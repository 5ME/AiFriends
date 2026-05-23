import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.character import Character
from web.views.utils.photo import remove_old_photo

logger = logging.getLogger(__name__)


class RemoveCharacterView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            character_id = request.data['character_id']
            try:
                character = Character.objects.get(id=character_id, author__user=request.user)
            except Character.DoesNotExist:
                return Response({'message': '角色不存在或无权访问'},
                                status=status.HTTP_404_NOT_FOUND)
            remove_old_photo(character.photo)
            remove_old_photo(character.background_image)
            character.delete()
            return Response({'message': 'success'})
        except Exception as e:
            logger.exception('删除角色异常: %s', e)
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
