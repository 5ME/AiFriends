from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.character import Character


class RemoveCharacterView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            character_id = request.data['character_id']
            Character.objects.get(id=character_id, author__user=request.user).delete()
            return Response({'message': 'success'})
        except:
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
