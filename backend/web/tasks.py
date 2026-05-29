"""Celery 任务入口 — autodiscover_tasks 自动扫描此模块"""
from web.views.friend.message.memory.tasks import update_memory_task  # noqa: F401
