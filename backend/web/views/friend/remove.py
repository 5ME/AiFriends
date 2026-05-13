from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

import logging

from web.models.friend import Friend

logger = logging.getLogger(__name__)


class FriendRemoveView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        try:
            friend_id = request.data['friend_id']
            Friend.objects.filter(id=friend_id, user_profile__user=request.user).delete()
            return Response({'message': 'success'})
        except Exception as e:
            logger.exception('删除好友异常: %s', e)
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
