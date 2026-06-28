from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
import logging

import redis
from django.conf import settings
from backend.celery import app

logger = logging.getLogger(__name__)


def _check_db():
    """PostgreSQL 连通性"""
    from django.db import connections
    connections['default'].cursor()
    return "ok"


def _check_redis():
    """Redis 连通性（使用限流 redis 客户端）"""
    r = redis.Redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=2,
    )
    r.ping()
    return "ok"


def _check_celery():
    """Celery worker 存活检测"""
    insp = app.control.inspect()
    stats = insp.ping()
    if not stats:
        raise RuntimeError("No Celery workers responding")
    return "ok"


def _run_checks(checks):
    """跑一组检查，返回 (result_dict, all_ok)。任一失败时 status 置 degraded。"""
    result = {"status": "ok"}
    all_ok = True
    for name, check_fn in checks:
        try:
            result[name] = check_fn()
        except Exception as e:
            logger.warning("健康检查 %s 失败: %s", name, e)
            result[name] = "error"
            all_ok = False
    if not all_ok:
        result["status"] = "degraded"
    return result, all_ok


class HealthView(APIView):
    """深度/聚合健康检查（DB + Redis + Celery）——供监控用，向后兼容。"""
    permission_classes = [AllowAny]

    def get(self, request):
        result, all_ok = _run_checks([
            ("db", _check_db),
            ("redis", _check_redis),
            ("celery", _check_celery),
        ])
        code = status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(result, status=code)


class LivenessView(APIView):
    """存活探测：进程能响应即视为存活，不查任何依赖。

    用于容器存活探测——依赖（DB/Redis/Celery）挂了不该重启应用：
    那种情况需要的是从 LB 摘除（见 readiness），重启进程无济于事。
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


class ReadinessView(APIView):
    """就绪探测：能否接流量——只查处理请求所必需的依赖（DB + Redis）。

    不查 Celery：Celery 挂只影响异步任务（如记忆摘要），不影响 HTTP/SSE 聊天，
    所以"能否接流量"不该因 Celery 而 false。
    """
    permission_classes = [AllowAny]

    def get(self, request):
        result, all_ok = _run_checks([
            ("db", _check_db),
            ("redis", _check_redis),
        ])
        code = status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(result, status=code)
