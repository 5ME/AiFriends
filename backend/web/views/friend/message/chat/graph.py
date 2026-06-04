import logging
import os
from typing import TypedDict, Annotated, Sequence

from django.utils.timezone import localtime, now
from langchain_core.messages import BaseMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.constants import START, END
from langgraph.graph import add_messages, StateGraph
from langgraph.prebuilt import InjectedState, ToolNode

from web.documents.utils.custom_embeddings import CustomEmbeddings

logger = logging.getLogger(__name__)

# LangGraph Chat Agent: LLM 决策 → tool 调用 → LLM 再决策的循环
class ChatGraph:
    @staticmethod
    def create_app():
        # Tool 1: 时间查询
        @tool
        def get_time() -> str:
            """
            当需要查询当前时间时，调用此函数。返回格式为：[年-月-日 时:分:秒]
            :return: 表示当前时间的字符串，格式为 %Y-%m-%d %H:%M:%S
            """
            return localtime(now()).strftime("%Y-%m-%d %H:%M:%S")

        # Tool 2: 知识库向量检索（pgvector）
        @tool
        def search_knowledge_base(query: str, state: Annotated[dict, InjectedState]) -> str:
            """
            在知识库中检索与用户问题相关的文档内容。
            知识库包含平台文档和用户上传的个人文档。
            当需要查找文档中的信息、引用资料或专业知识时，调用此函数。
            :param query: 要查询的问题
            :return: 查询结果
            """
            from web.models.document import DocumentChunk

            user_id = state.get("user_id")
            logger.info('RAG 知识库检索开始, query=%s, user_id=%s', query[:100], user_id)
            embeddings = CustomEmbeddings(user_id=user_id)
            emb = embeddings.embed_query(query)
            table = DocumentChunk._meta.db_table
            chunks = DocumentChunk.objects.raw(
                f"SELECT id, content, chunk_index, document_id "
                f"FROM {table} "
                f"WHERE owner_id IS NULL OR owner_id = %s "
                f"ORDER BY embedding <=> %s::vector LIMIT 3",
                [user_id, emb]
            )
            context = '\n\n'.join([f'内容片段：{i + 1}\n{c.content}' for i, c in enumerate(chunks)])
            return f'从知识库中找到以下相关信息：\n\n{context}\n\n'

        tools = [get_time, search_knowledge_base]

        # 主 LLM，负责决策和文本生成
        llm = ChatOpenAI(
            model="deepseek-v4-flash",
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
            user_id: int

        # Agent 节点：调用 LLM 产生响应或 tool 调用请求
        def model_call(state: AgentState) -> AgentState:
            logger.info('Chat Agent LLM 调用, message_count=%d', len(state["messages"]))
            res = llm.invoke(state["messages"])
            return {"messages": [res]}

        # 路由：LLM 响应中有 tool_calls 则转到工具节点，否则结束
        def should_continue(state: AgentState) -> str:
            last_message = state["messages"][-1]
            if last_message.tool_calls:
                return "tools"
            return "end"

        # LangGraph ToolNode 自动执行 tool_calls 并返回结果
        tool_node = ToolNode(tools)

        # 构建图: START → agent → tools ⇄ agent → END
        graph = StateGraph(AgentState)
        graph.add_node('agent', model_call)
        graph.add_node('tools', tool_node)

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
