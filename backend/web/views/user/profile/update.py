from django.contrib.auth.models import User
from django.utils.timezone import now
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.user import UserProfile
from web.views.utils.photo import remove_old_photo


class UpdateProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            user = request.user
            user_profile = UserProfile.objects.get(user=user)
            username = request.data.get('username').strip()
            profile = request.data.get('profile').strip()[:500]
            photo = request.FILES.get('photo', None)

            if not username:
                return Response({'message': '用户名不能为空'})
            if not profile:
                return Response({'message': '简介不能为空'})
            if username != user.username and User.objects.filter(username=username).exists():
                return Response({'message': '此用户名已存在'})

            user.username = username
            user.save()

            user_profile.profile = profile
            user_profile.updated_at = now()
            old_photo = ''
            if photo:
                old_photo = user_profile.photo
                user_profile.photo = photo
            user_profile.save()
            if old_photo:
                remove_old_photo(old_photo)
            return Response({
                'message': 'success',
                'user_id': user.id,
                'username': user.username,
                'profile': user_profile.profile,
                'photo': user_profile.photo.url,
            })
        except:
            return Response(data={'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
