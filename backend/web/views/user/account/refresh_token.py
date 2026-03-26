from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken


class RefreshTokenView(APIView):
    def post(self, request, *args, **kwargs):
        try:
            refresh_token = request.COOKIES['refresh_token']
            if not refresh_token:
                return Response({'message': 'refresh_token 不存在'},
                                status=status.HTTP_401_UNAUTHORIZED)
            # 框架自动刷新，如果 refresh_token 过期了，会报异常被下面捕获
            refresh = RefreshToken(refresh_token)
            response = Response({
                'message': 'success',
                'access_token': str(refresh.access_token)
            }, status=status.HTTP_200_OK)
            # 同时刷新 refresh_token
            if settings.SIMPLE_JWT['ROTATE_REFRESH_TOKENS']:
                # 在启用 refresh_token 轮换时，为当前 refresh 对象重新生成唯一的 jti（JWT ID），
                # 从而基于旧令牌对象产生一个全新的 refresh_token。旧令牌对应的 jti 将被服务端记录，
                # 确保旧令牌无法再次使用，符合 ROTATE_REFRESH_TOKENS 的安全要求。
                refresh.set_jti()
                response.set_cookie(key='refresh_token', value=str(refresh), httponly=True,
                                    samesite='Lax', max_age=86400 * 7, secure=True)
            return response
        except:
            return Response({'message': 'refresh_token 过期'},
                            status=status.HTTP_401_UNAUTHORIZED)
