import asyncio
import base64
import json
import os
import queue
import re
import threading
import time
import uuid
from typing import List, Dict

import websockets
from django.http import JsonResponse, StreamingHttpResponse
from langchain_core.messages import HumanMessage, BaseMessageChunk, BaseMessage, SystemMessage, AIMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BaseRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from websockets.client import ClientConnection

from web.models.friend import Friend, Message, SystemPrompt
from web.utils.quota import check_quota
from web.utils.usage import record_api_usage
from web.views.friend.message.chat.graph import ChatGraph
from web.views.friend.message.memory.tasks import update_memory_task
import logging

logger = logging.getLogger(__name__)

# 工具使用规则 — 注入为 Chat Agent 第一条 SystemMessage，优先级最高
TOOL_RULES = (
    "【知识库查询规则】\n"
    "你有 search_knowledge_base 工具可以查询知识库。\n"
    "1. 必须查询的情况：\n"
    "   - 用户询问专业知识、政策法规、技术原理、数据事实\n"
    "   - 用户提及文档内容、平台功能、操作指南\n"
    "   - 任何你不确定、需要查证的信息\n"
    "2. 可以不查的情况：\n"
    "   - 纯问候（\"你好\"\"早上好\"）\n"
    "   - 纯情感交流（\"我今天很难过\"）\n"
    "   - 纯闲聊（\"你喜欢吃什么\"）\n"
    "3. 不确定时宁可查询也不要遗漏。"
)

# 匹配 search_knowledge_base 返回的来源标记：[来源1: 文档标题 第3段]
CITATION_RE = re.compile(r'\[来源(\d+): (.+?) 第(\d+)段\]')


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
    为 Chat Agent 构建 3 层独立 SystemMessage：
    1. 工具使用规则（代码常量，最高优先级）
    2. 角色性格 + 长期记忆（Character.system_prompt + Friend.memory）
    3. 系统级框架约束（DB 单条 SystemPrompt.REPLY）
    """
    msgs = inputs['messages']
    system_msgs = []

    # 第 1 条：工具使用规则（代码常量，最高优先级）
    system_msgs.append(SystemMessage(TOOL_RULES))

    # 第 2 条：角色性格 + 长期记忆
    personality = friend.character.system_prompt.strip()
    memory = (friend.memory or "").strip()
    personality_parts = []
    if personality:
        personality_parts.append(f"【角色性格】\n{personality}")
    if memory:
        personality_parts.append(f"【与用户的长期记忆】\n{memory}")
    if personality_parts:
        system_msgs.append(SystemMessage("\n\n".join(personality_parts)))

    # 第 3 条：系统级框架（DB 单条）
    framework = SystemPrompt.objects.filter(
        title=SystemPrompt.Title.REPLY
    ).first()
    if framework and framework.prompt.strip():
        system_msgs.append(SystemMessage(framework.prompt))

    return {**inputs, 'messages': system_msgs + msgs}


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

    return {**inputs, 'messages': new_msgs}


class MessageChatView(APIView):
    permission_classes = (IsAuthenticated,)
    renderer_classes = (SSERenderer,)

    def post(self, request, *args, **kwargs):
        friend_id = request.data.get("friend_id")
        message = (request.data.get("message") or "").strip()
        if not friend_id or not message:
            return Response({"message": "参数不完整"},
                            status=status.HTTP_400_BAD_REQUEST)
        # select_related 预加载 character→voice，避免后续 add_system_prompt 和 voice_id 延迟查询
        friends = Friend.objects.filter(pk=friend_id, user_profile__user=request.user) \
                      .select_related('character__voice')
        if not friends.exists():
            logger.warning('好友关系不存在(角色可能已被删除), friend_id=%s, user_id=%s', friend_id, request.user.id)
            response = StreamingHttpResponse(
                self._error_stream('该角色已被创建者删除，相关好友关系已解除'),
                content_type='text/event-stream'
            )
            response['Cache-Control'] = 'no-cache'
            return response
        friend = friends.first()
        # === 用户每日 LLM 配额检查 ===
        allowed, cur, limit = check_quota(friend.user_profile_id, 'llm')
        if not allowed:
            return JsonResponse(
                {'message': f'今日对话配额已用尽({cur}/{limit})，请明天再试'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        app = ChatGraph.create_app()
        inputs = {
            'messages': [HumanMessage(message)],
            'user_id': friend.user_profile.id,
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

    def _error_stream(self, error_msg: str):
        error_data = json.dumps({'error': error_msg}, ensure_ascii=False)
        yield f'data: {error_data}\n\n'
        yield 'data: [DONE]\n\n'

    # 定义流式生成器
    def event_stream(
            self,
            app: CompiledStateGraph,
            inputs,
            friend: Friend,
            message: str
    ):
        start_time = time.time()
        mq = queue.Queue(maxsize=500)
        logger.info('Chat Agent 开始, friend_id=%s', friend.id)
        voice_id = friend.character.voice.voice_id if friend.character.voice else ''
        user_id = friend.user_profile_id
        thread = threading.Thread(
            target=self.work, args=(app, inputs, mq, voice_id, user_id),
            daemon=True,  # 非 daemon 线程会在 worker 退出时阻止进程关闭
        )
        thread.start()

        full_output = []
        full_usage = {}
        has_error = False
        error_message = ''

        while True:
            msg = mq.get()
            # print('====>', msg)
            if msg is None:
                break
            # 转发 RAG 引用来源到 SSE（在 content 之前到达，前端可提前展示来源）
            if msg.get('citations', None):
                yield f'data: {json.dumps({"citations": msg["citations"]}, ensure_ascii=False)}\n\n'
            if msg.get('error', None):
                has_error = True
                error_message = msg['error']
                yield f'data: {json.dumps({"error": error_message}, ensure_ascii=False)}\n\n'
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
        duration_ms = int((time.time() - start_time) * 1000)
        record_api_usage(
            user_id=user_id,
            api_type='llm',
            model_name='deepseek-v4-flash',
            token_count=total_tokens,
            duration_ms=duration_ms,
            success=not has_error,
            error_message=error_message,
        )
        try:
            Message.objects.create(
                friend=friend,
                user_message=message[:5000],
                input=[m.model_dump() for m in inputs['messages']],
                output=''.join(full_output)[:5000],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            )
        except Exception:
            logger.exception('聊天消息保存失败, friend_id=%s', friend.id)
        logger.info('Chat Agent 完成, friend_id=%s, tokens: in=%d out=%d total=%d',
                    friend.id, input_tokens, output_tokens, total_tokens)
        msg_count = Message.objects.filter(friend=friend).count()
        if msg_count % 10 == 0:
            logger.info('触发 Memory 更新, friend_id=%s, message_count=%d',
                        friend.id, msg_count)
            update_memory_task.delay(friend.id)

    def work(
            self,
            app: CompiledStateGraph,
            inputs,
            mq: queue.Queue,
            voice_id: str,
            user_id: int,
    ):
        # === TTS 配额检查（sync 上下文，避免 async 内调 ORM） ===
        tts_allowed, _, _ = check_quota(user_id, 'tts')
        if not tts_allowed:
            logger.warning('TTS 跳过：今日配额已用尽, user_id=%s', user_id)
        try:
            asyncio.run(self.run_tts_task(app, inputs, mq, voice_id, user_id, tts_allowed))
        except Exception:
            logger.exception('Chat Agent 执行异常')
            try:
                mq.put({'error': '系统异常，请稍后重试'})
            except queue.Full:
                logger.warning('队列满，错误消息丢弃')
        finally:
            mq.put(None)  # 阻塞确保哨兵送达；消费者死掉时 daemon 线程随 worker 退出清理
        # TTS usage 在同步上下文中写入（避免 async 中调 ORM 的 SynchronousOnlyOperation）
        if hasattr(self, '_tts_usage'):
            record_api_usage(**self._tts_usage)
            del self._tts_usage

    async def run_tts_task(
            self,
            app: CompiledStateGraph,
            inputs,
            mq: queue.Queue,
            voice_id: str,
            user_id: int,
            tts_allowed: bool = True,
    ):
        task_id = uuid.uuid4().hex
        if not tts_allowed:
            # 跳过 TTS：只跑 LLM 文字流，TTS usage 不记录（无 _tts_usage）
            await self._stream_llm_only(app, inputs, mq, user_id)
            return
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
                        "rate": 1.0,  # 语速
                        "pitch": 1  # 音调
                    },
                    "input": {  # input不能省去，不然会报错
                    }
                }
            }))
            logger.info('TTS WebSocket 已连接, task_id=%s, voice_id=%s', task_id, voice_id)
            async for msg in ws:
                if json.loads(msg)['header']['event'] == 'task-started':
                    break
            await asyncio.gather(
                self.tts_sender(ws, task_id, app, inputs, mq, user_id),
                self.tts_receiver(ws, mq)
            )

    async def tts_sender(
            self,
            ws,
            task_id: str,
            app: CompiledStateGraph,
            inputs,
            mq: queue.Queue,
            user_id: int,
    ):
        start = time.time()
        total_chars = 0
        success = True
        error_message = ''
        try:
            async for msg, metadata in app.astream(inputs, stream_mode="messages"):
                # 检测知识库检索结果 ToolMessage，提取引用来源
                # LangGraph 时序：ToolMessage 在第一个 AIMessageChunk 之前到达，
                # 确保 citations 事件先于 content 发送到前端
                if isinstance(msg, ToolMessage) and msg.name == "search_knowledge_base":
                    citations = []
                    for m in CITATION_RE.finditer(msg.content):
                        citations.append({
                            "index": int(m.group(1)),
                            "title": m.group(2),
                            "chunk_index": int(m.group(3)),
                        })
                    if citations:
                        mq.put_nowait({'citations': citations})

                elif isinstance(msg, BaseMessageChunk):
                    if msg.content:
                        total_chars += len(msg.content)
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
        except Exception as e:
            success = False
            error_message = str(e)[:500]
            raise
        finally:
            duration_ms = int((time.time() - start) * 1000)
            self._tts_usage = {
                'user_id': user_id,
                'api_type': 'tts',
                'model_name': 'cosyvoice-v3-flash',
                'token_count': total_chars,
                'duration_ms': duration_ms,
                'success': success,
                'error_message': error_message,
            }

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

    async def _stream_llm_only(
            self,
            app: CompiledStateGraph,
            inputs,
            mq: queue.Queue,
            user_id: int,
    ):
        """仅 LLM 文字流的降级路径 — TTS 配额超限或 TTS 失败时使用。"""
        try:
            async for msg, metadata in app.astream(inputs, stream_mode="messages"):
                if isinstance(msg, ToolMessage) and msg.name == "search_knowledge_base":
                    citations = []
                    for m in CITATION_RE.finditer(msg.content):
                        citations.append({
                            "index": int(m.group(1)),
                            "title": m.group(2),
                            "chunk_index": int(m.group(3)),
                        })
                    if citations:
                        mq.put_nowait({'citations': citations})

                elif isinstance(msg, BaseMessageChunk):
                    if msg.content:
                        mq.put_nowait({'content': msg.content})
                    if hasattr(msg, 'usage_metadata') and msg.usage_metadata:
                        mq.put_nowait({'usage': msg.usage_metadata})
        except Exception:
            logger.exception('LLM 文字流异常（TTS 降级模式）')
            try:
                mq.put_nowait({'error': '系统异常，请稍后重试'})
            except queue.Full:
                pass
