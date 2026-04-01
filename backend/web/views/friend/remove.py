from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.friend import Friend


class FriendRemoveView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        try:
            friend_id = request.data['friend_id']
            Friend.objects.filter(id=friend_id, user_profile__user=request.user).delete()
            return Response({'message': 'success'})
        except:
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
