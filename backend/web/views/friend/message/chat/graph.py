import os
from typing import TypedDict, Annotated, Sequence

from django.utils.timezone import localtime, now
from langchain_core.messages import BaseMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.constants import START, END
from langgraph.graph import add_messages, StateGraph
from langgraph.prebuilt import ToolNode


class ChatGraph:
    @staticmethod
    def create_app():
        @tool
        def get_time() -> str:
            """
            当需要查询当前时间时，调用此函数。返回格式为：[年-月-日 时:分:秒]
            :return: 表示当前时间的字符串，格式为 %Y-%m-%d %H:%M:%S
            """
            return localtime(now()).strftime("%Y-%m-%d %H:%M:%S")

        tools = [get_time]

        llm = ChatOpenAI(
            model="deepseek-v3.2",
            api_key=os.getenv("API_KEY"),
            base_url=os.getenv("API_BASE"),
            streaming=True,  # 流式输出
            model_kwargs={
                "stream_options": {
                    "include_usage": True,  # 输出token消耗量
                }
            }
        ).bind_tools(tools)

        class AgentState(TypedDict):
            messages: Annotated[Sequence[BaseMessage], add_messages]

        def model_call(state: AgentState) -> AgentState:
            from pprint import pprint
            pprint(state)
            res = llm.invoke(state["messages"])
            return {"messages": [res]}

        def should_continue(state: AgentState) -> str:
            last_message = state["messages"][-1]
            if last_message.tool_calls:
                return "tools"
            return "end"

        # 工具节点
        tool_node = ToolNode(tools)

        graph = StateGraph(AgentState)
        # 添加节点
        graph.add_node('agent', model_call)
        graph.add_node('tools', tool_node)

        # 添加边
        graph.add_edge(START, 'agent')
        graph.add_conditional_edges(
            'agent',
            should_continue,
            {
                'tools': 'tools',
                'end': END
            }
        )
        graph.add_edge('tools', 'agent')

        return graph.compile()
