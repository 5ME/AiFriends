import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.friend import Friend

logger = logging.getLogger(__name__)


class FriendGetCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            character_id = request.query_params.get('character_id')
            friend_count = Friend.objects.filter(character_id=character_id).count()
            return Response({
                'message': 'success',
                'friend_count': friend_count,
            })
        except Exception as e:
            logger.exception('获取好友数异常: %s', e)
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
