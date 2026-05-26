import json
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from web.tests.conftest import _MockASRWebSocket


def _dummy_audio():
    """生成一小段假 PCM 音频数据 (SimpleUploadedFile)"""
    return SimpleUploadedFile("audio", b"\x00\x00" * 160, content_type="audio/pcm")


class TestASREndpoint:
    """POST /api/friend/message/asr/asr/"""

    @patch("web.views.friend.message.asr.asr.websockets.connect")
    def test_asr_success(self, mock_ws_connect, auth_client, mock_asr_ws):
        mock_ws_connect.return_value = mock_asr_ws

        resp = auth_client.post(
            "/api/friend/message/asr/asr/",
            {"audio": _dummy_audio()},
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["text"] == "你好"

    def test_asr_missing_audio(self, auth_client):
        resp = auth_client.post("/api/friend/message/asr/asr/", {})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_asr_requires_auth(self, api_client):
        resp = api_client.post(
            "/api/friend/message/asr/asr/",
            {"audio": _dummy_audio()},
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("web.views.friend.message.asr.asr.websockets.connect")
    def test_asr_transcription_concat(self, mock_ws_connect, auth_client):
        """多个 sentence_end 片段正确拼接"""
        mock_ws = _MockASRWebSocket(messages=[
            json.dumps({"header": {"event": "task-started"}}),
            json.dumps({
                "header": {"event": "result-generated"},
                "payload": {
                    "output": {
                        "transcription": {
                            "sentence_end": False,
                            "text": "中间",
                        }
                    }
                }
            }),
            json.dumps({
                "header": {"event": "result-generated"},
                "payload": {
                    "output": {
                        "transcription": {
                            "sentence_end": True,
                            "text": "第一句",
                        }
                    }
                }
            }),
            json.dumps({
                "header": {"event": "result-generated"},
                "payload": {
                    "output": {
                        "transcription": {
                            "sentence_end": True,
                            "text": "第二句",
                        }
                    }
                }
            }),
            json.dumps({"header": {"event": "task-finished"}}),
        ])
        mock_ws_connect.return_value = mock_ws

        resp = auth_client.post(
            "/api/friend/message/asr/asr/",
            {"audio": _dummy_audio()},
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["text"] == "第一句第二句"

    @patch("web.views.friend.message.asr.asr.websockets.connect")
    def test_asr_task_failed(self, mock_ws_connect, auth_client):
        """task-failed 事件返回 500"""
        mock_ws = _MockASRWebSocket(messages=[
            json.dumps({"header": {"event": "task-started"}}),
            json.dumps({"header": {"event": "task-failed"}}),
        ])
        mock_ws_connect.return_value = mock_ws

        resp = auth_client.post(
            "/api/friend/message/asr/asr/",
            {"audio": _dummy_audio()},
        )
        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
