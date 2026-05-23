import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.character import Character, Voice

logger = logging.getLogger(__name__)


class GetSingleCharacterView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            character_id = request.query_params.get('character_id')
            try:
                character = Character.objects.get(id=character_id, author__user=request.user)
            except Character.DoesNotExist:
                return Response({'message': '角色不存在或无权访问'},
                                status=status.HTTP_404_NOT_FOUND)
            voices_raw = Voice.objects.order_by('id')
            voices = []
            for voice in voices_raw:
                voices.append({
                    'id': voice.id,
                    'name': voice.name,
                    'profile': voice.profile,
                })
            return Response({
                'message': 'success',
                'character': {
                    'id': character.id,
                    'name': character.name,
                    'introduction': character.introduction,
                    'system_prompt': character.system_prompt,
                    'photo': character.photo_url,
                    'background_image': character.background_image_url,
                    'voice_id': character.voice.id,
                },
                'voices': voices,
            })
        except Exception as e:
            logger.exception('获取角色详情异常: %s', e)
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
