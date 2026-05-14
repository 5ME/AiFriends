import logging
import os
from typing import TypedDict, Annotated, Sequence

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.constants import START, END
from langgraph.graph import add_messages
from langgraph.graph.state import CompiledStateGraph, StateGraph

logger = logging.getLogger(__name__)

# LangGraph Memory Agent: 对聊天历史做摘要压缩，写入 Friend.memory
class MemoryGraph:
    @staticmethod
    def create_app() -> CompiledStateGraph:
        # 使用小模型做摘要，降低成本
        llm = ChatOpenAI(
            model='tongyi-xiaomi-analysis-flash',
            api_key=os.getenv('API_KEY'),
            base_url=os.getenv('API_BASE'),
        )

        class AgentState(TypedDict):
            messages: Annotated[Sequence[BaseMessage], add_messages]

        # 单节点：接收系统提示词 + 历史消息，输出摘要
        def model_call(state: AgentState) -> AgentState:
            logger.info('Memory Agent LLM 调用, message_count=%d', len(state["messages"]))
            res = llm.invoke(state["messages"])
            return {'messages': [res]}

        # START → agent → END，单向无循环
        graph = StateGraph(AgentState)
        graph.add_node('agent', model_call)

        graph.add_edge(START, 'agent')
        graph.add_edge('agent', END)

        return graph.compile()
