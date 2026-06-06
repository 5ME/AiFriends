import logging
import os
from typing import TypedDict, Annotated, Sequence

from django.db import connection

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

            知识库包含：
            - 平台官方文档（使用说明、功能指南）
            - 用户上传的个人文档（工作资料、学习笔记等）

            必须调用此工具的情况：
            - 用户询问任何关于政策、法规、制度、标准的问题
            - 用户询问专业知识、技术原理、行业规范
            - 用户提到"文档""资料""查一下""找一下""有没有相关"
            - 用户问题需要事实依据或数据支撑
            - 你不确定答案、需要查证时

            不需要调用的情况：
            - 纯问候、告别（"你好""再见"）
            - 纯情感倾诉（"我今天心情不好"）
            - 纯角色扮演闲聊（"你喜欢什么颜色"）
            """
            from web.models.document import DocumentChunk, UserDocument
            from web.models.retrieval_trace import RetrievalTrace

            user_id = state.get("user_id")
            logger.info('RAG 知识库检索开始, query=%s, user_id=%s', query[:100], user_id)

            embeddings = CustomEmbeddings(user_id=user_id)
            emb = embeddings.embed_query(query)

            chunk_table = DocumentChunk._meta.db_table
            doc_table = UserDocument._meta.db_table

            # 使用 cursor 执行 JOIN 查询，一次拿到 title + distance
            with connection.cursor() as cursor:
                cursor.execute(f"""
                    SELECT dc.id, dc.content, dc.chunk_index, dc.document_id,
                           ud.title AS document_title,
                           dc.embedding <=> %s::vector AS distance
                    FROM {chunk_table} dc
                    LEFT JOIN {doc_table} ud ON dc.document_id = ud.id
                    WHERE dc.owner_id IS NULL OR dc.owner_id = %s
                    ORDER BY dc.embedding <=> %s::vector
                    LIMIT 3
                """, [emb, user_id, emb])
                rows = cursor.fetchall()

            if not rows:
                return "知识库中未找到相关信息。"

            parts = ["从知识库中找到以下相关信息：\n"]
            for i, row in enumerate(rows):
                _, content, chunk_index, document_id, title, distance = row
                # 明确 if/elif/else 构建来源标签（避免三目运算符优先级歧义）
                if title:
                    source_label = title
                elif document_id:
                    source_label = f"文档{document_id}"
                else:
                    source_label = "系统知识库"
                # chunk_index 在 DB 中为 0-based，展示时转为 1-based
                parts.append(f"[来源{i+1}: {source_label} 第{chunk_index + 1}段]")
                parts.append(content)
                parts.append("")

                # 写入检索 trace（fail-safe：DB 故障不影响工具返回值）
                if document_id:
                    try:
                        RetrievalTrace.objects.create(
                            user_id=user_id,
                            query=query,
                            document_id=document_id,
                            chunk_index=chunk_index,
                            distance=float(distance),
                        )
                    except Exception:
                        logger.exception(
                            'RetrievalTrace 写入失败, document_id=%s', document_id
                        )

            logger.info('RAG 检索完成, hits=%d', len(rows))
            return "\n".join(parts)

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
