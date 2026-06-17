"""Celery 定时任务 — 聚合前一天 APIUsage → APIUsageDaily 并删除过期记录"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Sum
from django.utils import timezone

from backend.celery import app
from web.models.usage import APIUsage, APIUsageDaily

logger = logging.getLogger(__name__)


@app.task
def cleanup_usage_task():
    """聚合昨天的 APIUsage → APIUsageDaily，删除 90 天前的原始记录。

    Celery Beat 每天凌晨 2:00 调度。幂等 — 聚合使用 ignore_conflicts=True。
    """
    today = timezone.localdate()

    # 先聚合再删除：确保数据已写入 APIUsageDaily 再清理过期明细
    yesterday = today - timedelta(days=1)
    try:
        aggregate_usage(yesterday)
    except Exception:
        # 聚合失败时跳过删除，保护原始数据不丢失
        logger.exception('cleanup_usage: 聚合失败，跳过删除以保护数据')
        return

    # 删除 API_USAGE_RETENTION_DAYS 天前的 APIUsage 原始记录（默认 90 天）
    try:
        cutoff = today - timedelta(days=settings.API_USAGE_RETENTION_DAYS)
        delete_old_records(cutoff)
    except Exception:
        logger.exception('cleanup_usage: 删除过期记录失败')


def aggregate_usage(date):
    """聚合指定日期的 APIUsage → APIUsageDaily（幂等）。

    按 (user, api_type) 分组，使用 bulk_create(ignore_conflicts=True)
    基于 UniqueConstraint 保证重复运行不报错、不重复插入。
    """
    rows = (
        APIUsage.objects
        .filter(created_at__date=date)
        .values('user', 'api_type')
        .annotate(
            total_tokens=Sum('token_count'),
            call_count=Count('id'),
            total_duration_ms=Sum('duration_ms'),
        )
    )

    if not rows:
        logger.info('cleanup_usage: 日期 %s 无 APIUsage 记录，跳过聚合', date)
        return

    batch = [
        APIUsageDaily(
            date=date,
            user_id=r['user'],
            api_type=r['api_type'],
            total_tokens=r['total_tokens'],
            call_count=r['call_count'],
            total_duration_ms=r['total_duration_ms'],
        )
        for r in rows
    ]

    # PostgreSQL 中 NULL != NULL，UniqueConstraint 对 NULL 列不生效，
    # 因此 ignore_conflicts=True 无法防止 user=NULL 行重复插入。
    # 先删除同日期 user=NULL 的行，确保系统调用聚合也幂等。
    APIUsageDaily.objects.filter(date=date, user=None).delete()

    # ignore_conflicts=True + UniqueConstraint(date, user, api_type)
    # 使聚合幂等：重复运行同一日期不会报错，也不会重复插入
    APIUsageDaily.objects.bulk_create(batch, ignore_conflicts=True)
    logger.info(
        'cleanup_usage: 日期 %s 聚合完成，%d 行写入 APIUsageDaily',
        date, len(batch),
    )


def delete_old_records(cutoff):
    """删除 created_at__date < cutoff 的 APIUsage 原始记录。

    使用 Django __date 查找将 timezone-aware DateTimeField
    转换为日期进行比较，正确处理时区。
    """
    deleted, _ = (
        APIUsage.objects
        .filter(created_at__date__lt=cutoff)
        .delete()
    )
    # Django delete() 返回 (total_deleted, per_model_counts)
    count = deleted
    if count > 0:
        logger.info(
            'cleanup_usage: 删除 %d 条 %s 之前的 APIUsage 记录',
            count, cutoff,
        )
    else:
        logger.info('cleanup_usage: 无 %s 之前的过期记录', cutoff)
