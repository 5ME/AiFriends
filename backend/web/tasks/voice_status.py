"""复刻音色的状态刷新 —— 用 Beat 周期任务，不用长轮询。

为什么不用"提交后起一个 Celery 任务轮询到出结果"：`CELERY_TASK_SOFT_TIME_LIMIT=120` /
`TIME_LIMIT=180`、worker 是 `-c 1`，长轮询会被硬超时杀掉，还会堵住文档处理与记忆总结。
实测（2026-09-17）阿里云侧从提交到 OK 约 15 秒，所以 5 分钟的节奏只会让界面上的"审核中"
多显示一会儿，不影响正确性。
"""
import logging
import os

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

BATCH_LIMIT = 20                  # 单轮上限
FRESH_HOURS = 24                  # 只处理 24 小时内创建的行
QUERY_TIMEOUT = 3                 # 单条查询超时
WATERMARK = 800                   # 全平台音色数告警水位（1000 是账号级上限）


def query_status(voice_id):
    """返回阿里云侧的 status（'OK' / 'DEPLOYING' / 'UNDEPLOYED'）。"""
    import requests

    resp = requests.post(
        os.getenv('VOICE_URL'),
        headers={'Authorization': f'Bearer {os.getenv("API_KEY")}'},
        json={'model': 'voice-enrollment',
              'input': {'action': 'query_voice', 'voice_id': voice_id}},
        timeout=QUERY_TIMEOUT)
    return ((resp.json().get('output') or {}).get('status') or '').upper()


@shared_task
def refresh_deploying_voices():
    from web.models.character import Voice

    cutoff = timezone.now() - timezone.timedelta(hours=FRESH_HOURS)
    rows = list(Voice.objects.filter(status='deploying', created_at__gte=cutoff)
                .order_by('created_at')[:BATCH_LIMIT])
    if not rows:
        return {'checked': 0}

    total = Voice.objects.count()
    if total >= WATERMARK:
        logger.warning('音色总数已达水位: %d（账号上限 1000，请清理）', total)

    checked = changed = 0
    for v in rows:
        checked += 1
        try:
            st = query_status(v.voice_id)
        except Exception:
            logger.exception('查询音色状态失败，保持原状态: voice=%s', v.id)
            continue                          # fail-open：单条失败不影响其余
        if st == 'OK' and v.status != 'ready':
            v.status = 'ready'
            v.save(update_fields=['status'])
            changed += 1
        elif st == 'UNDEPLOYED' and v.status != 'rejected':
            v.status = 'rejected'
            v.save(update_fields=['status'])
            changed += 1
    return {'checked': checked, 'changed': changed}
