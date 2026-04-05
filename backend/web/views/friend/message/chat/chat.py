import json

from django.http import StreamingHttpResponse
from langchain_core.messages import HumanMessage, BaseMessageChunk
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BaseRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.friend import Friend, Message
from web.views.friend.message.chat.graph import ChatGraph


class SSERenderer(BaseRenderer):
    media_type = 'text/event-stream'
    format = 'txt'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


class MessageChatView(APIView):
    permission_classes = (IsAuthenticated,)
    renderer_classes = (SSERenderer,)

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

        # 定义流式生成器
        def event_stream():
            full_output = []
            full_usage = {}
            for msg, metadata in app.stream(inputs, stream_mode="messages"):
                if isinstance(msg, BaseMessageChunk):
                    if msg.content:
                        full_output.append(msg.content)
                        yield f'data: {json.dumps({'content': msg.content}, ensure_ascii=False)}\n\n'
                    if hasattr(msg, 'usage_metadata') and msg.usage_metadata:
                        full_usage = msg.usage_metadata
            yield 'data: [DONE]\n\n'
            input_tokens = full_usage.get('input_tokens', 0)
            output_tokens = full_usage.get('output_tokens', 0)
            total_tokens = full_usage.get('total_tokens', 0)
            Message.objects.create(
                friend=friend,
                user_message=message[:5000],
                input=json.dumps(
                    [m.model_dump() for m in inputs['messages']],
                    ensure_ascii=False
                )[:50000],
                output=''.join(full_output)[:5000],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            )

        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        return response
