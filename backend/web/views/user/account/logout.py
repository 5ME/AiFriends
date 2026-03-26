from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class LogoutView(APIView):
    # 需要登录
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        response = Response({'message': 'success'},
                            status=status.HTTP_200_OK)
        response.delete_cookie(key='refresh_token')
        return response
