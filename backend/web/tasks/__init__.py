"""Celery 任务入口 — autodiscover_tasks 自动扫描此模块及其子包"""
from web.views.friend.message.memory.tasks import update_memory_task  # noqa: F401
from web.views.document.tasks import process_document_task  # noqa: F401
