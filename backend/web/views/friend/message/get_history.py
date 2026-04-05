from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.friend import Message


class GetHistoryView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        try:
            last_message_id = int(request.query_params.get('last_message_id', 0))
            friend_id = request.query_params.get('friend_id')
            queryset = Message.objects.filter(friend_id=friend_id, friend__user_profile__user=request.user)
            if last_message_id > 0:
                queryset = queryset.filter(pk__lt=last_message_id)
            message_raw = queryset.order_by('-id')[:10]
            messages = []
            for message in message_raw:
                messages.append({
                    'id': message.id,
                    'user_message': message.user_message,
                    'output': message.output,
                })
            return Response({'message': 'success', 'messages': messages})
        except:
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
