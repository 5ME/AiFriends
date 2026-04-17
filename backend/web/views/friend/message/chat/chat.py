import asyncio
import base64
import json
import os
import queue
import threading
import uuid
from typing import List, Dict

import websockets
from django.http import StreamingHttpResponse
from langchain_core.messages import HumanMessage, BaseMessageChunk, BaseMessage, SystemMessage, AIMessage
from langgraph.graph.state import CompiledStateGraph
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BaseRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from websockets.client import ClientConnection

from web.models.friend import Friend, Message, SystemPrompt
from web.views.friend.message.chat.graph import ChatGraph
from web.views.friend.message.memory import update


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
    prompts.append(f'【长期记忆】\n{friend.memory}\n')
    prompt = ''.join(prompts)
    return {'messages': [SystemMessage(prompt)] + msgs}


def add_recent_messages(
        inputs: Dict[str, List[BaseMessage]],
        friend: Friend,
        recent_count: int,
) -> dict[str, List[BaseMessage]]:
    """
    添加最近对话记录到输入消息中。
    逻辑：将历史记录插入到系统提示词之后，当前用户消息之前。

    :param inputs:
    :param friend:
    :param recent_count: 指定最近对话记录的条数
    :return:
    """
    msgs = list(inputs['messages'])  # 拷贝一份防止修改原引用
    if not msgs:
        return inputs

    messages_raw = list(Message.objects.filter(friend=friend).order_by('-id')[:recent_count])
    messages_raw.reverse()

    history = []
    for m in messages_raw:
        if m.user_message:
            history.append(HumanMessage(m.user_message))
        if m.output:
            history.append(AIMessage(m.output))

    # 健壮性逻辑：
    # 1. 如果第一条是 SystemMessage，则在它后面插入历史
    # 2. 否则，直接在最前面插入历史
    if isinstance(msgs[0], SystemMessage):
        new_msgs = [msgs[0]] + history + msgs[1:]
    else:
        new_msgs = history + msgs

    return {'messages': new_msgs}


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

        response = StreamingHttpResponse(
            self.event_stream(app, inputs, friend, message),
            content_type='text/event-stream'
        )
        # 禁用浏览器和中间缓存，确保流式内容的实时性
        response['Cache-Control'] = 'no-cache'
        # 禁用 Nginx 等代理服务器的响应缓冲，实现即时下发
        response['X-Accel-Buffering'] = 'no'
        return response

    # 定义流式生成器
    def event_stream(
            self,
            app: CompiledStateGraph,
            inputs,
            friend: Friend,
            message: str
    ):
        mq = queue.Queue()
        thread = threading.Thread(target=self.work, args=(app, inputs, mq, friend.character.voice.voice_id))
        thread.start()

        full_output = []
        full_usage = {}

        while True:
            msg = mq.get()
            # print('====>', msg)
            if msg is None:
                break
            if msg.get('content', None):
                full_output.append(msg['content'])
                yield f'data: {json.dumps({'content': msg['content']}, ensure_ascii=False)}\n\n'
            if msg.get('audio', None):
                yield f'data: {json.dumps({'audio': msg['audio']}, ensure_ascii=False)}\n\n'
            if msg.get('usage', None):
                full_usage = msg['usage']

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
        if Message.objects.filter(friend=friend).count() % 1 == 0:
            update.update_memory(friend)

    def work(
            self,
            app: CompiledStateGraph,
            inputs,
            mq: queue.Queue,
            voice_id: str,
    ):
        try:
            asyncio.run(self.run_tts_task(app, inputs, mq, voice_id))
        finally:
            mq.put_nowait(None)

    async def run_tts_task(
            self,
            app: CompiledStateGraph,
            inputs,
            mq: queue.Queue,
            voice_id: str,
    ):
        task_id = uuid.uuid4().hex
        wss_url = os.getenv('WSS_URL')
        api_key = os.getenv('API_KEY')
        headers = {'Authorization': f'Bearer {api_key}'}
        async with websockets.connect(wss_url, additional_headers=headers) as ws:
            await ws.send(json.dumps({
                "header": {
                    "action": "run-task",
                    "task_id": task_id,  # 随机uuid
                    "streaming": "duplex"
                },
                "payload": {
                    "task_group": "audio",
                    "task": "tts",
                    "function": "SpeechSynthesizer",
                    "model": "cosyvoice-v3-flash",
                    "parameters": {
                        "text_type": "PlainText",
                        "voice": voice_id,  # 音色
                        "format": "mp3",  # 音频格式
                        "sample_rate": 22050,  # 采样率
                        "volume": 50,  # 音量
                        "rate": 1.25,  # 语速
                        "pitch": 1  # 音调
                    },
                    "input": {  # input不能省去，不然会报错
                    }
                }
            }))
            async for msg in ws:
                if json.loads(msg)['header']['event'] == 'task-started':
                    break
            await asyncio.gather(
                self.tts_sender(ws, task_id, app, inputs, mq),
                self.tts_receiver(ws, mq)
            )

    async def tts_sender(
            self,
            ws,
            task_id: str,
            app: CompiledStateGraph,
            inputs,
            mq: queue.Queue
    ):
        async for msg, metadata in app.astream(inputs, stream_mode="messages"):
            if isinstance(msg, BaseMessageChunk):
                if msg.content:
                    await ws.send(json.dumps({
                        "header": {
                            "action": "continue-task",
                            "task_id": task_id,  # 随机uuid
                            "streaming": "duplex"
                        },
                        "payload": {
                            "input": {
                                "text": msg.content,
                            }
                        }
                    }))
                    mq.put_nowait({'content': msg.content})
                if hasattr(msg, 'usage_metadata') and msg.usage_metadata:
                    mq.put_nowait({'usage': msg.usage_metadata})
        await ws.send(json.dumps({
            "header": {
                "action": "finish-task",
                "task_id": task_id,
                "streaming": "duplex"
            },
            "payload": {
                "input": {}  # input不能省去，否则会报错
            }
        }))

    async def tts_receiver(
            self,
            ws,
            mq: queue.Queue
    ):
        async for msg in ws:
            if isinstance(msg, bytes):
                audio = base64.b64encode(msg).decode('utf-8')
                mq.put_nowait({'audio': audio})
            else:
                data = json.loads(msg)
                event = data['header']['event']
                if event in ['task-finished', 'task-failed']:
                    break
