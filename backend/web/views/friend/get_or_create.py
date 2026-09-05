from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

import logging

from web.models.character import Character
from web.models.friend import Friend
from web.models.user import UserProfile

logger = logging.getLogger(__name__)


class FriendGetOrCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            character_id = request.data.get('character_id')
            if not character_id:
                return Response({'message': '参数不完整'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not Character.objects.filter(id=character_id).exists():
                logger.warning('角色已被删除, character_id=%s, user_id=%s', character_id, request.user.id)
                return Response({'message': '该角色已被创建者删除'},
                                status=status.HTTP_404_NOT_FOUND)
            user_profile = UserProfile.objects.get(user=request.user)
            # select_related 一次性 JOIN character→author→user，避免链式延迟加载
            friends = Friend.objects.filter(character_id=character_id, user_profile=user_profile) \
                          .select_related('character__author__user')
            if friends.exists():
                friend = friends.first()
            else:
                friend = Friend.objects.create(character_id=character_id, user_profile=user_profile)
            return Response({
                'message': 'success',
                'friend': {
                    'id': friend.id,
                    'character': {
                        'id': friend.character.id,
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
                }
            })
        except Exception as e:
            logger.exception('获取或创建好友异常: %s', e)
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
