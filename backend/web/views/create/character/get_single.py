from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.character import Character


class GetSingleCharacterView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            character_id = request.query_params.get('character_id')
            character = Character.objects.get(id=character_id, author__user=request.user)
            return Response({
                'message': 'success',
                'character': {
                    'id': character.id,
                    'name': character.name,
                    'profile': character.profile,
                    'photo': character.photo.url,
                    'background_image': character.background_image.url,
                }
            })
        except:
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
