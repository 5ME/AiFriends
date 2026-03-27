from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from web.models.user import UserProfile


class RegisterView(APIView):
    def post(self, request, *args, **kwargs):
        try:
            username = request.data.get('username').strip()
            password = request.data.get('password').strip()
            if not username or not password:
                return Response({'message': '用户名和密码不能为空'})
            if User.objects.filter(username=username).exists():
                return Response({'message': '此用户名已被占用'})
            print(username, password)
            user = User.objects.create_user(username=username, password=password)
            print(user)
            user_profile = UserProfile.objects.create(user=user)
            print(user_profile)
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
        except:
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
