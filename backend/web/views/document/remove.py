"""POST /api/document/remove/ — 删除文档及其 chunks"""
import logging
import os

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.document import UserDocument
from backend.celery import app

logger = logging.getLogger(__name__)


class DocumentRemoveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        doc_id = request.data.get('id')
        try:
            doc = UserDocument.objects.get(
                id=doc_id, owner=request.user.userprofile
            )
        except UserDocument.DoesNotExist:
            return Response(
                {'message': '文档不存在或无权访问'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 撤销正在排队的 Celery 任务（只判断 task_id 非空，不判断 status）
        # status='failed' 时 task_id 非空 = retry pending，同样需要撤销
        if doc.celery_task_id:
            try:
                app.control.revoke(doc.celery_task_id)
                logger.info('已撤销 Celery 任务, doc_id=%d, task_id=%s',
                            doc.id, doc.celery_task_id)
            except Exception:
                logger.warning('撤销 Celery 任务失败, doc_id=%d, task_id=%s',
                               doc.id, doc.celery_task_id, exc_info=True)

        # 删除 media 文件
        if doc.file_url:
            file_path = os.path.join(settings.MEDIA_ROOT, doc.file_url)
            if os.path.exists(file_path):
                os.remove(file_path)

        # 级联删除 DocumentChunks（Django CASCADE）
        doc.delete()
        logger.info('文档已删除, doc_id=%s, title=%s', doc_id, doc.title)

        return Response({'message': '删除成功'})
