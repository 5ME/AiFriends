from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.user import UserProfile

import logging
logger = logging.getLogger(__name__)


class GetUserInfoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            user_profile = UserProfile.objects.get(user=user)
            return Response({
                'message': 'success',
                'user_id': user.id,
                'username': user.username,
                'photo': user_profile.photo_url,
                'profile': user_profile.profile,
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception('获取用户信息异常: %s', e)
            return Response({"message": "系统异常"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
