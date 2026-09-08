"""Message.citations 后端批次（Q3/Q4）测试。

覆盖：
- extract_citations 纯函数解析（多块/空/无标记/块间空行/缺标题）
- work() 断连路径（cancel_event set）落库含 citations：正常 TTS 路径 + 降级路径
"""
import json
import queue
import threading
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage

from web.models.friend import Message
from web.views.friend.message.chat.chat import MessageChatView, extract_citations


# 与 graph.search_knowledge_base 返回格式一致的样例工具内容
TOOL_CONTENT = (
    "从知识库中找到以下相关信息：\n\n"
    "[来源1: 社保政策.pdf 第1段]\n社保制度介绍...\n\n"
    "[来源2: 就业指南.md 第5段]\n养老保险说明...\n"
)


def _drain_queue(mq):
    """模拟断连后无消费者的场景 — work() 结尾 mq.put(None) 阻塞，由本线程取走。"""
    while True:
        if mq.get() is None:
            return


class TestExtractCitations:
    """extract_citations 纯函数解析"""

    def test_multi_block_parsing(self):
        """2 个来源块 → 2 条四元组，content = 标记行后正文"""
        citations = extract_citations(TOOL_CONTENT)
        assert citations == [
            {'index': 1, 'title': '社保政策.pdf', 'chunk_index': 1,
             'content': '社保制度介绍...'},
            {'index': 2, 'title': '就业指南.md', 'chunk_index': 5,
             'content': '养老保险说明...'},
        ]

    def test_no_marker_returns_empty(self):
        """无 [来源] 标记的文本 → []"""
        assert extract_citations('知识库中未找到相关信息。') == []

    def test_empty_string_returns_empty(self):
        """空串 / 纯空白 → []"""
        assert extract_citations('') == []
        assert extract_citations('   \n  ') == []

    def test_blank_lines_between_blocks(self):
        """块间空行不影响解析（引导文本块跳过，正文块正常）"""
        content = "[来源1: 文档A.pdf 第2段]\n正文A\n\n\n\n[来源2: 文档B.pdf 第3段]\n正文B"
        citations = extract_citations(content)
        assert len(citations) == 2
        assert citations[0]['content'] == '正文A'
        assert citations[1]['content'] == '正文B'

    def test_marker_without_title_skipped(self):
        """标记行缺标题 → 无法匹配，块被跳过（与旧 finditer 行为一致，不抛异常）"""
        assert extract_citations('[来源1: 第1段]\n正文') == []

    def test_system_knowledge_title(self):
        """系统知识库来源 title 为 '系统知识库'"""
        citations = extract_citations('[来源1: 系统知识库 第1段]\n系统内容...')
        assert citations == [
            {'index': 1, 'title': '系统知识库', 'chunk_index': 1,
             'content': '系统内容...'},
        ]


@pytest.mark.django_db
class TestWorkDisconnectCitations:
    """P1-3 / C2：断连路径（cancel_event set）消息落库且含 citations"""

    @pytest.fixture
    def view(self):
        return MessageChatView()

    def _inputs_dict(self, text='测试'):
        return {'messages': [HumanMessage(content=text)]}

    def _run_work_with_drain(self, view, mock_app, friend, user_profile,
                             cancel_event, mq, inputs_dict):
        """调用 work()，并用后台线程取走结尾的 None 哨兵（模拟断连后无消费者）。"""
        drain = threading.Thread(target=_drain_queue, args=(mq,), daemon=True)
        drain.start()
        view.work(
            mock_app, inputs_dict, mq, voice_id='test',
            user_id=user_profile.id, cancel_event=cancel_event,
            friend=friend, message='测试', inputs_dict=inputs_dict,
        )
        drain.join(timeout=5)

    @patch('web.views.friend.message.chat.chat.check_quota')
    def test_disconnect_degraded_path_saves_message_with_citations(
            self, mock_check, view, friend, user_profile, mocker):
        """TTS 配额耗尽降级路径 + 断连 → 消息仍落库且含 citations（P1-3 缺陷修复）"""
        mock_check.return_value = (False, 10_000, 10_000)  # TTS 配额耗尽

        async def mock_astream(inputs, stream_mode):
            yield ToolMessage(
                content=TOOL_CONTENT, name='search_knowledge_base',
                tool_call_id='call_1'), {}
            yield AIMessageChunk(content='根据资料回答'), {}
            last = AIMessageChunk(content='。')
            last.usage_metadata = {
                'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15,
            }
            yield last, {}

        mock_app = mocker.MagicMock()
        mock_app.astream = mock_astream

        cancel_event = threading.Event()
        cancel_event.set()  # 断连
        mq = queue.Queue()
        self._run_work_with_drain(
            view, mock_app, friend, user_profile, cancel_event, mq,
            self._inputs_dict(),
        )

        msg = Message.objects.filter(friend=friend).order_by('-id').first()
        assert msg is not None
        assert msg.output == '根据资料回答。'
        assert msg.citations == extract_citations(TOOL_CONTENT)
        # usage 落库自 _output_usage
        assert msg.total_tokens == 15

    @patch('web.views.friend.message.chat.chat.check_quota')
    @patch('web.views.friend.message.chat.chat.websockets.connect')
    def test_disconnect_tts_path_saves_message_with_citations(
            self, mock_ws_connect, mock_check, view, friend, user_profile, mocker):
        """正常 TTS 路径 + 断连 → 消息落库且含 citations，且不再发送 TTS 内容"""
        mock_check.return_value = (True, 0, 10_000)  # TTS 配额充足

        # Mock TTS WebSocket：task-started（run_tts_task）→ task-finished（tts_receiver）
        mock_ws = mocker.AsyncMock()
        call_counter = [0]

        async def ws_async_iterator():
            call_counter[0] += 1
            if call_counter[0] == 1:
                yield json.dumps({'header': {'event': 'task-started'}})
            else:
                yield json.dumps({'header': {'event': 'task-finished'}})

        mock_ws.__aiter__ = ws_async_iterator
        mock_ws.send = mocker.AsyncMock()
        mock_ws_connect.return_value = mock_ws

        async def mock_astream(inputs, stream_mode):
            yield ToolMessage(
                content=TOOL_CONTENT, name='search_knowledge_base',
                tool_call_id='call_1'), {}
            yield AIMessageChunk(content='回复内容'), {}

        mock_app = mocker.MagicMock()
        mock_app.astream = mock_astream

        cancel_event = threading.Event()
        cancel_event.set()  # 断连
        mq = queue.Queue()
        self._run_work_with_drain(
            view, mock_app, friend, user_profile, cancel_event, mq,
            self._inputs_dict(),
        )

        msg = Message.objects.filter(friend=friend).order_by('-id').first()
        assert msg is not None
        assert msg.output == '回复内容'
        assert msg.citations == extract_citations(TOOL_CONTENT)
        # 断连时不发送 continue-task（TTS 内容），finish-task 仍发送解锁 receiver
        continue_calls = [c for c in mock_ws.send.call_args_list
                          if '"continue-task"' in str(c.args[0])]
        assert len(continue_calls) == 0
