"""Memory Agent 异步任务 — Celery Worker 中执行，不阻塞聊天请求"""
import logging

from langchain_core.messages import SystemMessage, HumanMessage
from openai import APIStatusError
from backend.celery import app

from web.models.friend import Friend, Message, SystemPrompt
from web.views.friend.message.memory.graph import MemoryGraph

logger = logging.getLogger(__name__)


def create_system_message() -> SystemMessage:
    system_prompts = SystemPrompt.objects.filter(
        title=SystemPrompt.Title.MEMORY
    ).order_by('order_number')
    prompts = [sp.prompt for sp in system_prompts]
    return SystemMessage(content="".join(prompts))


def create_human_message(friend: Friend) -> HumanMessage:
    """构造 Memory Agent 输入：原始记忆 + 上次摘要之后的增量对话"""
    prompts = [f'【原始记忆】\n{friend.memory or ""}\n', f'【最近对话】\n']
    total_msgs = Message.objects.filter(friend=friend).count()

    # 从上次摘要位置开始取 — 失败重试时不会遗漏消息
    skip = friend.last_summarized_count
    take = min(total_msgs - skip, 30)  # 30 条兜底，防 LLM 上下文溢出

    messages_raw = Message.objects.filter(friend=friend).order_by('id')[skip:skip + take]
    for m in messages_raw:
        prompts.append(f'user: {m.user_message}\n')
        prompts.append(f'ai: {m.output}\n')
    return HumanMessage(content="".join(prompts))


@app.task(max_retries=1)
def update_memory_task(friend_id: int):
    """异步更新好友记忆摘要。失败由下一次触发自然重试。"""
    try:
        friend = Friend.objects.get(id=friend_id)
        msg_count = Message.objects.filter(friend=friend).count()
        logger.info('Memory 任务开始, friend_id=%d, msg_count=%d', friend_id, msg_count)

        app_graph = MemoryGraph.create_app()
        inputs = {
            'messages': [create_system_message(), create_human_message(friend)]
        }
        res = app_graph.invoke(inputs)
        friend.memory = res['messages'][-1].content

        # 使用任务开始时的快照计数，避免 LLM 调用期间新消息导致计数偏大
        friend.last_summarized_count = msg_count
        friend.save()

        logger.info('Memory 任务完成, friend_id=%d, memory_len=%d',
                    friend_id, len(friend.memory or ''))
    except Exception as exc:
        logger.exception('Memory 任务失败, friend_id=%d', friend_id)
        # 4xx 客户端错误（400/401/403/404 等）是永久性故障，重试无意义
        # 但 429 RateLimit 是临时限流，应重试
        if isinstance(exc, APIStatusError) and 400 <= exc.status_code < 500 and exc.status_code != 429:
            return
        # 5xx、网络超时、429 限流等临时故障 → 10s 后重试一次
        raise update_memory_task.retry(exc=exc, countdown=10)
