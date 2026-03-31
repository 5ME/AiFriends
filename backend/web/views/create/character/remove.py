from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.character import Character
from web.views.utils.photo import remove_old_photo


class RemoveCharacterView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            character_id = request.data['character_id']
            character = Character.objects.get(id=character_id, author__user=request.user)
            remove_old_photo(character.photo)
            remove_old_photo(character.background_image)
            character.delete()
            return Response({'message': 'success'})
        except:
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
