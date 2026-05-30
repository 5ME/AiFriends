"""GET /api/document/list/ — 返回当前用户的文档列表"""
import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.document import UserDocument

logger = logging.getLogger(__name__)


class DocumentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        docs = UserDocument.objects.filter(
            owner=request.user.userprofile
        ).order_by('-created_at')

        result = [{
            'id': d.id,
            'title': d.title,
            'file_type': d.file_type,
            'status': d.status,
            'error_message': d.error_message,
            'chunks_count': d.chunks_count,
            'created_at': d.created_at.isoformat(),
        } for d in docs]

        return Response({'documents': result})
