"""POST /api/document/upload/ — 用户上传文档，触发 Celery 异步处理"""
import logging
import os
import uuid

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.document import UserDocument
from web.views.document.tasks import process_document_task

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'txt', 'md', 'pdf'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# 魔数校验：文件头字节 → 预期值
MAGIC_BYTES = {
    'pdf': b'%PDF',
    'txt': None,   # 不含 null byte 即可
    'md': None,    # 同上
}


def _validate_file(file) -> str | None:
    """同步校验上传文件，返回错误消息；无错返回 None"""
    if not file:
        return '请选择文件'
    if file.size == 0:
        return '文件为空'
    if file.size > MAX_FILE_SIZE:
        return '文件大小不能超过 10MB'

    # 扩展名只提取一次，后续复用
    ext = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else ''
    if ext not in ALLOWED_EXTENSIONS:
        return '不支持的文件格式，仅支持 txt/md/pdf'

    expected_magic = MAGIC_BYTES.get(ext)
    if expected_magic is not None:
        header = file.read(4)
        file.seek(0)
        if not header.startswith(expected_magic):
            return '文件格式与扩展名不匹配'
    elif expected_magic is None:
        # txt/md: 检测是否为纯文本（不含 null byte）
        header = file.read(512)
        file.seek(0)
        if b'\x00' in header:
            return '文件格式与扩展名不匹配'

    return None


def sanitize_title(raw_name: str) -> str:
    """从原始文件名提取安全的 title，防路径遍历，截断到 200 字符"""
    basename = os.path.basename(raw_name)
    return basename[:200]


def save_to_media(file, ext: str) -> str:
    """保存上传文件到 media/documents/<uuid>.<ext>，返回相对路径"""
    from django.conf import settings
    filename = f'{uuid.uuid4().hex}.{ext}'
    dir_path = os.path.join(settings.MEDIA_ROOT, 'documents')
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, filename)
    with open(file_path, 'wb') as f:
        for chunk in file.chunks():
            f.write(chunk)
    return f'documents/{filename}'


class DocumentUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        file = request.FILES.get('file')

        error = _validate_file(file)
        if error:
            return Response({'message': error}, status=status.HTTP_400_BAD_REQUEST)

        ext = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else ''

        doc = UserDocument.objects.create(
            owner=request.user.userprofile,
            title=sanitize_title(file.name),
            file_url=save_to_media(file, ext),
            file_type=ext,
            status='pending',
        )

        try:
            task = process_document_task.delay(doc.id)
            doc.celery_task_id = task.id
            doc.save(update_fields=['celery_task_id'])
        except Exception as e:
            logger.exception('Celery 任务投递失败, doc_id=%d', doc.id)
            doc.status = 'failed'
            doc.error_message = f'任务投递失败: {str(e)[:500]}'
            doc.save(update_fields=['status', 'error_message'])
            return Response(
                {'message': '文件已上传但异步处理启动失败，请稍后重试'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        logger.info('文档上传成功, doc_id=%d, title=%s', doc.id, doc.title)
        return Response(
            {'id': doc.id, 'title': doc.title, 'status': doc.status},
            status=status.HTTP_201_CREATED,
        )
