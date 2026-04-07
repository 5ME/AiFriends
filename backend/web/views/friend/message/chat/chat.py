import json
from typing import List, Dict

from django.http import StreamingHttpResponse
from langchain_core.messages import HumanMessage, BaseMessageChunk, BaseMessage, SystemMessage, AIMessage
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BaseRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.friend import Friend, Message, SystemPrompt
from web.views.friend.message.chat.graph import ChatGraph


class SSERenderer(BaseRenderer):
    media_type = 'text/event-stream'
    format = 'txt'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


def add_system_prompt(
        inputs: Dict[str, List[BaseMessage]],
        friend: Friend,
) -> dict[str, List[BaseMessage]]:
    """
    添加系统提示到输入消息中

    参数:
    inputs: 包含消息列表的字典，格式为 {'messages': [BaseMessage(...)]}
    friend: 验证通过的好友模型实例

    返回:
    更新后的inputs字典，包含添加的系统提示
    """
    msgs = inputs['messages']
    system_prompts = SystemPrompt.objects.filter(title__exact='回复').order_by('order_number')
    prompts = []
    for sp in system_prompts:
        prompts.append(sp.prompt)
    prompts.append(f'\n\n【角色性格】\n\n{friend.character.profile}\n')
    prompt = ''.join(prompts)
    return {'messages': [SystemMessage(prompt)] + msgs}


def add_recent_messages(
        inputs: Dict[str, List[BaseMessage]],
        friend: Friend,
        recent_count: int,
) -> dict[str, List[BaseMessage]]:
    """
    添加最近对话记录到输入消息中

    :param inputs:
    :param friend:
    :param recent_count: 指定最近对话记录的条数
    :return:
    """
    msgs = inputs['messages']
    messages_raw = list(Message.objects.filter(friend=friend).order_by('-id')[:recent_count])
    messages_raw.reverse()
    messages = []
    for m in messages_raw:
        messages.append(HumanMessage(m.user_message))
        messages.append(AIMessage(m.output))
    return {'messages': msgs[:1] + messages + msgs[-1:]}


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
        # 添加系统提示词
        inputs = add_system_prompt(inputs, friend)
        # 添加最近对话记录
        inputs = add_recent_messages(inputs, friend, 10)

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
