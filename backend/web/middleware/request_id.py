import uuid
import threading
import logging

logger = logging.getLogger(__name__)

_local = threading.local()


def get_request_id():
    """供日志 Filter 调用，无活跃请求时返回 '-'"""
    return getattr(_local, 'request_id', '-')


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.request_id = uuid.uuid4().hex
        request.request_id = _local.request_id
        response = self.get_response(request)
        response['X-Request-ID'] = _local.request_id
        return response


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = get_request_id()
        return True
