from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from web.models.user import UserProfile


class LoginView(APIView):
    def post(self, request, *args, **kwargs):
        try:
            username = request.data.get('username').strip()
            password = request.data.get('password').strip()
            if not username or not password:
                return Response({'message': '用户名和密码不能为空'},
                                status=status.HTTP_400_BAD_REQUEST)
            user = authenticate(username=username, password=password)
            if user:
                user_profile = UserProfile.objects.get(user=user)
                refresh = RefreshToken.for_user(user)
                response = Response({
                    'message': 'success',
                    'access_token': str(refresh.access_token),
                    'user_id': user.id,
                    'username': user.username,
                    'photo': user_profile.photo.url,
                    'profile': user_profile.profile,
                }, status=status.HTTP_200_OK)
                response.set_cookie(key='refresh_token', value=str(refresh), httponly=True,
                                    samesite='Lax', max_age=86400 * 7, secure=True)
                return response
            else:
                return Response({'message': '用户名或密码错误'},
                                status=status.HTTP_200_OK)
        except:
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
