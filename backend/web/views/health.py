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


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        checks = [
            ("db", _check_db),
            ("redis", _check_redis),
            ("celery", _check_celery),
        ]

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
            return Response(result, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(result)
