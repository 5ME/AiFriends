import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.views.create.character.voice.serializer import serialize_voice
from web.views.create.character.voice.visibility import visible_voices

logger = logging.getLogger(__name__)


class GetListVoiceView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        try:
            profile = request.user.userprofile
            voices = [serialize_voice(v, profile) for v in visible_voices(profile)]
            return Response({"message": "success", "voices": voices})
        except Exception as e:
            logger.exception('获取音色列表异常: %s', e)
            return Response({"message": "系统异常"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
