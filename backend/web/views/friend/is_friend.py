from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

import logging

from web.models.friend import Friend
from web.models.user import UserProfile

logger = logging.getLogger(__name__)


class FriendIsFriendView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            character_id = request.query_params.get('character_id')
            user_profile = UserProfile.objects.get(user=request.user)
            friend = Friend.objects.filter(character_id=character_id, user_profile=user_profile).first()
            return Response({
                'message': 'success',
                'is_friend': friend is not None,
                'friend_id': friend.id if friend else None,
            })
        except Exception as e:
            logger.exception('检查好友关系异常: %s', e)
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
