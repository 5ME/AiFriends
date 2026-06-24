import json
import logging
import os
from typing import TypedDict, Annotated, Sequence

from django.conf import settings
from django.db import connection

from django.utils.timezone import localtime, now
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.constants import START, END
from langgraph.graph import add_messages, StateGraph
from langgraph.prebuilt import InjectedState, ToolNode

from web.documents.utils.custom_embeddings import CustomEmbeddings

logger = logging.getLogger(__name__)


def retrieve_chunks(
    query_text: str,
    top_k: int = 5,
    user_id: int | None = None,      # owner 过滤 +（track_usage 时）embedding usage 归属
    include_system: bool = True,      # 是否同时召回系统知识库（owner_id IS NULL）
    track_usage: bool = True,         # 是否记录 embedding usage（评估传 False 避免污染生产用量）
) -> list[dict]:
    """RAG 检索核心：embedding + pgvector 余弦排序 → 结构化 top-k。

    不做阈值过滤、不格式化、不写 trace —— 这些由调用方负责。
    线上工具 search_knowledge_base 与离线评估 rag_eval 共用此函数，
    保证评估的就是真实生产检索逻辑。
    """
    from web.models.document import DocumentChunk, UserDocument

    # 兜底防 LIMIT 0/负数；上限钳制属信任边界，由调用方（如 search_knowledge_base）负责
    top_k = max(1, top_k)
    # track_usage=False 时以 user_id=None 创建 embeddings，避免评估流量写入生产 APIUsage
    emb_user_id = user_id if track_usage else None
    embeddings = CustomEmbeddings(user_id=emb_user_id)
    emb = embeddings.embed_query(query_text)

    chunk_table = DocumentChunk._meta.db_table
    doc_table = UserDocument._meta.db_table

    # include_system 决定是否召回系统知识库（owner_id IS NULL）；
    # 评估传 include_system=False，只查 eval owner，避免真实系统库混入评估结果
    if include_system:
        where_clause = "dc.owner_id IS NULL OR dc.owner_id = %s"
    else:
        where_clause = "dc.owner_id = %s"

    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT dc.id, dc.content, dc.chunk_index, dc.document_id,
                   ud.title AS document_title,
                   dc.embedding <=> %s::vector AS distance,
                   dc.metadata
            FROM {chunk_table} dc
            LEFT JOIN {doc_table} ud ON dc.document_id = ud.id
            WHERE {where_clause}
            ORDER BY dc.embedding <=> %s::vector
            LIMIT %s
        """, [emb, user_id, emb, top_k])
        rows = cursor.fetchall()

    results = []
    for row in rows:
        chunk_id, content, chunk_index, document_id, title, distance, metadata = row
        # cursor 直接查 JSONField 返回的是 JSON 字符串，需解析为 dict
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}
        results.append({
            'chunk_id': chunk_id,
            'content': content,
            'chunk_index': chunk_index,
            'document_id': document_id,
            'title': title,
            'distance': distance,
            'metadata': metadata or {},
        })
    return results


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
        def search_knowledge_base(
            query: str,
            max_results: int = None,
            # state 由 LangGraph ToolNode 注入，给默认值以满足「默认参数后不可接非默认参数」的语法约束
            state: Annotated[dict, InjectedState] = None,
        ) -> str:
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

            根据问题类型选择 max_results：简单事实查询传 1-2，需要多角度信息传 3-5。
            """
            # max_results 缺省时回退到配置默认值
            default_max = getattr(settings, 'RAG_DEFAULT_MAX_RESULTS', 5)
            if max_results is None:
                max_results = default_max
            # 钳制 LLM 传入的值到 [1, default_max]（不可信输入，信任边界在工具层）
            max_results = max(1, min(max_results, default_max))

            from web.models.retrieval_trace import RetrievalTrace

            user_id = state.get("user_id")
            logger.info('RAG 知识库检索开始, query=%s, user_id=%s', query[:100], user_id)

            # 调共享检索核心：线上召回 系统库 + 当前用户，并记录 embedding usage
            rows = retrieve_chunks(
                query, top_k=max_results, user_id=user_id,
                include_system=True, track_usage=True,
            )

            # 按余弦距离阈值过滤不相关结果
            threshold = getattr(settings, 'RAG_SIMILARITY_THRESHOLD', 0.5)
            rows = [r for r in rows if r['distance'] < threshold]

            if not rows:
                return "知识库中未找到相关信息。请尝试更换关键词后重新检索。"

            parts = ["从知识库中找到以下相关信息：\n"]
            for i, row in enumerate(rows):
                content = row['content']
                chunk_index = row['chunk_index']
                document_id = row['document_id']
                title = row['title']
                distance = row['distance']
                # 明确 if/elif/else 构建来源标签
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
                # 统计已完成的工具调用次数，超过上限强制结束，防止异常循环
                tool_call_count = sum(
                    1 for msg in state["messages"]
                    if isinstance(msg, ToolMessage)
                )
                if tool_call_count >= getattr(settings, 'RAG_MAX_TOOL_CALLS', 5):
                    return "end"  # 强制结束，让 LLM 基于已有信息回复
                return "tools"
            return "end"

        # LangGraph ToolNode 自动执行 tool_calls 并返回结果
        tool_node = ToolNode(tools)

        # 构建图: START → agent → tools ⇄ agent → END
        # agent ⇄ tools 循环受 RAG_MAX_TOOL_CALLS 上限保护（见 should_continue）
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
