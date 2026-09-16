import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.character import Voice
from web.views.create.character.voice.serializer import serialize_voice

logger = logging.getLogger(__name__)


class GetListVoiceView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        try:
            voices = [serialize_voice(v) for v in Voice.objects.order_by('id')]
            return Response({"message": "success", "voices": voices})
        except Exception as e:
            logger.exception('获取音色列表异常: %s', e)
            return Response({"message": "系统异常"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
