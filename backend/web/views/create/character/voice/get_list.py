from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.character import Voice


class GetListVoiceView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        try:
            voices_raw = Voice.objects.order_by('id')
            voices = []
            for voice in voices_raw:
                voices.append({
                    'id': voice.id,
                    'name': voice.name,
                    'profile': voice.profile,
                })
            return Response({"message": "success", "voices": voices})
        except:
            return Response({"message": "系统异常"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
