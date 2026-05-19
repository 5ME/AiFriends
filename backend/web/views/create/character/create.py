import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.character import Character, Voice
from web.models.user import UserProfile

logger = logging.getLogger(__name__)


class CreateCharacterView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            user = request.user
            user_profile = UserProfile.objects.get(user=user)
            name = request.data.get('name').strip()
            introduction = request.data.get('introduction', '').strip()
            system_prompt = request.data.get('system_prompt', '').strip()
            photo = request.FILES.get('photo', None)
            background_image = request.FILES.get('background_image', None)
            voice_id = request.data.get('voice_id')

            if not name:
                return Response({'message': '角色名称不能为空'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not introduction:
                return Response({'message': '角色简介不能为空'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not system_prompt:
                return Response({'message': '角色信息不能为空'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not photo:
                return Response({'message': '角色头像不能为空'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not background_image:
                return Response({'message': '对话背景不能为空'},
                                status=status.HTTP_400_BAD_REQUEST)

            voice = Voice.objects.get(id=voice_id)

            character = Character.objects.create(
                author=user_profile, name=name,
                introduction=introduction, system_prompt=system_prompt,
                photo=photo, background_image=background_image, voice=voice
            )
            return Response({'message': 'success'})
        except Exception as e:
            logger.exception('创建角色异常: %s', e)
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
