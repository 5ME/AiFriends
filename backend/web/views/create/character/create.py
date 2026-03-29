from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.character import Character
from web.models.user import UserProfile


class CreateCharacterView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            user = request.user
            user_profile = UserProfile.objects.get(user=user)
            name = request.data.get('name').strip()
            profile = request.data.get('profile').strip()
            photo = request.FILES.get('photo', None)
            background_image = request.FILES.get('background_image', None)

            if not name:
                return Response({'message': '角色名称不能为空'})
            if not profile:
                return Response({'message': '角色信息不能为空'})
            if not photo:
                return Response({'message': '角色头像不能为空'})
            if not background_image:
                return Response({'message': '对话背景不能为空'})

            character = Character.objects.create(
                author=user_profile, name=name, profile=profile, photo=photo,
                background_image=background_image
            )
            return Response({'message': 'success'})
        except:
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
