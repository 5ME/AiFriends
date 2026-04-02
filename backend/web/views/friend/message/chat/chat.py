from langchain_core.messages import HumanMessage
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.friend import Friend
from web.views.friend.message.chat.graph import ChatGraph


class MessageChatView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        friend_id = request.data["friend_id"]
        message = request.data["message"].strip()
        if not message:
            return Response({"message": "消息不能为空"})
        friends = Friend.objects.filter(pk=friend_id, user_profile__user=request.user)
        if not friends.exists():
            return Response({"message": "好友关系不存在"})
        friend = friends.first()
        app = ChatGraph.create_app()
        inputs = {
            'messages': [HumanMessage(message)]
        }
        res = app.invoke(inputs)
        print(res['messages'][-1].content)
        return Response({'message': 'success'})
