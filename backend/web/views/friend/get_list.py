from django.db.models import Max
from django.db.models.functions import Coalesce
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

import logging

from web.models.friend import Friend

logger = logging.getLogger(__name__)


class FriendGetListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            items_count = int(request.query_params.get('items_count', 0))
            # select_related 一次性 JOIN character→author→user，避免循环中逐条查 3 次
            friends_raw = Friend.objects.filter(user_profile__user=request.user) \
                              .select_related('character__author__user') \
                              .annotate(last_active=Coalesce(Max('message__created_at'), 'created_at')) \
                              .order_by('-last_active')[items_count:items_count + 20]
            friends = []
            for friend in friends_raw:
                friends.append({
                    'id': friend.id,
                    'character': {
                        'id': friend.character_id,
                        'name': friend.character.name,
                        'introduction': friend.character.introduction,
                        'photo': friend.character.photo_url,
                        'background_image': friend.character.background_image_url,
                        'author': {
                            'user_id': friend.character.author.user_id,
                            'username': friend.character.author.user.username,
                            'photo': friend.character.author.photo_url,
                        }
                    }
                })
            return Response({'message': 'success', 'friends': friends})
        except Exception as e:
            logger.exception('获取好友列表异常: %s', e)
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
