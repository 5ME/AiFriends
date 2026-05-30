"""文档处理 Celery 异步任务"""
from backend.celery import app


@app.task(max_retries=1)
def process_document_task(doc_id: int):
    """文档异步处理 — 占位，完整实现在 Task 7"""
    pass
