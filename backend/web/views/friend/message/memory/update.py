from django.utils.timezone import now
from langchain_core.messages import SystemMessage, HumanMessage

from web.models.friend import Friend, SystemPrompt, Message
from web.views.friend.message.memory.graph import MemoryGraph


def create_system_message() -> SystemMessage:
    system_prompts = SystemPrompt.objects.filter(title__exact='记忆').order_by('order_number')
    prompts = []
    for sp in system_prompts:
        prompts.append(sp.prompt)
    return SystemMessage(content="".join(prompts))


def create_human_message(friend: Friend, recent_count: int=10) -> HumanMessage:
    prompts = [f'【原始记忆】\n{friend.memory}\n', f'【最近对话】\n']
    messages_raw = list(Message.objects.filter(friend=friend).order_by('-id')[:recent_count])
    messages_raw.reverse()
    for m in messages_raw:
        prompts.append(f'user: {m.user_message}\n')
        prompts.append(f'ai: {m.output}\n')
    return HumanMessage(content="".join(prompts))


def update_memory(friend: Friend):
    app = MemoryGraph.create_app()
    inputs = {
        'messages': [
            create_system_message(),
            create_human_message(friend)
        ]
    }
    res = app.invoke(inputs)
    friend.memory = res['messages'][-1].content
    friend.updated_at = now()
    friend.save()
