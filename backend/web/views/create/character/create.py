import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.character import Character, Voice
from web.models.user import UserProfile
from web.views.create.character.voice.visibility import is_voice_visible

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
            voice_pk = request.data.get('voice')

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
            if not voice_pk:
                return Response({'message': '角色音色不能为空'},
                                status=status.HTTP_400_BAD_REQUEST)

            try:
                voice = Voice.objects.get(id=voice_pk)
            except (Voice.DoesNotExist, ValueError, TypeError):
                return Response({'message': '音色不存在或无权访问'},
                                status=status.HTTP_404_NOT_FOUND)
            if not is_voice_visible(voice, user_profile):
                # message 必须与上面的"不存在"逐字相同 —— 否则 404 就成了存在性探测器
                return Response({'message': '音色不存在或无权访问'},
                                status=status.HTTP_404_NOT_FOUND)
            if voice.status != 'ready':
                # 可见但没就绪 → 400（与 404 区分开：一个该换，一个该等）
                return Response({'message': '该音色尚不可用（审核中 / 审核未通过）'},
                                status=status.HTTP_400_BAD_REQUEST)

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
