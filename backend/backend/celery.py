import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

app = Celery('backend')

# namespace='CELERY' → settings 中所有 CELERY_ 开头的配置自动注入
app.config_from_object('django.conf:settings', namespace='CELERY')

# 自动扫描所有 INSTALLED_APPS 中的 tasks.py
app.autodiscover_tasks()
