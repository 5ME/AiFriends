import logging

from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.character import Character

logger = logging.getLogger(__name__)


class HomepageIndexView(APIView):
    def get(self, request):
        try:
            items_count = int(request.query_params.get('items_count', 0))
            search_text = request.query_params.get('search_text', '').strip()
            if search_text:
                queryset = Character.objects.filter(
                    Q(name__icontains=search_text) | Q(introduction__icontains=search_text)
                )
            else:
                queryset = Character.objects.all()
            # select_related 一次性 JOIN author+user，避免 N+1 查询
            # 也防止多次网络往返中远程 PG 断连
            characters_raw = (queryset
                .select_related('author__user')
                .order_by('-id')[items_count:items_count + 20])
            characters = []
            for character in characters_raw:
                characters.append({
                    'id': character.id,
                    'name': character.name,
                    'introduction': character.introduction,
                    'photo': character.photo_url,
                    'background_image': character.background_image_url,
                    'author': {
                        'user_id': character.author_id,
                        'username': character.author.user.username,
                        'photo': character.author.photo.url
                    }
                })
            return Response({'message': 'success', 'characters': characters})
        except Exception as e:
            logger.exception('首页加载异常: %s', e)
            return Response({"message": "系统异常"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
