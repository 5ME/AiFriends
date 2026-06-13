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

    @patch("web.views.friend.message.asr.asr.record_api_usage")
    @patch("web.views.friend.message.asr.asr.websockets.connect")
    def test_asr_usage_uses_userprofile_id(
        self, mock_ws_connect, mock_record, auth_client, user, db, mock_asr_ws,
    ):
        """ASR usage 应记录 UserProfile.id 而非 User.id（防止 FK 错账）"""
        from django.contrib.auth.models import User
        from web.models.user import UserProfile

        mock_ws_connect.return_value = mock_asr_ws

        # 构造 User.id != UserProfile.id 的场景：
        # 创建一个 dummy User+UserProfile 占位，使 UserProfile 自增序列偏移
        dummy_user = User.objects.create_user(username="asr_test_dummy")
        UserProfile.objects.create(user=dummy_user)

        # 删除测试用户的 Profile 并重建，使其获得一个不同于 User.id 的新 id
        old_up = UserProfile.objects.get(user=user)
        old_up.delete()
        new_up = UserProfile.objects.create(user=user)
        assert user.id != new_up.id, "前置条件失败：User.id 应不等于 UserProfile.id"

        resp = auth_client.post(
            "/api/friend/message/asr/asr/",
            {"audio": _dummy_audio()},
        )
        assert resp.status_code == status.HTTP_200_OK
        mock_record.assert_called_once()
        assert mock_record.call_args[1]["user_id"] == new_up.id, (
            f"应传 UserProfile.id({new_up.id})，而非 User.id({user.id})"
        )

    @patch("web.views.friend.message.asr.asr.check_quota")
    def test_quota_exceeded_returns_429(self, mock_check, auth_client):
        """ASR 配额超限 → 429"""
        mock_check.return_value = (False, 300, 300)
        resp = auth_client.post(
            "/api/friend/message/asr/asr/",
            {"audio": _dummy_audio()},
        )
        assert resp.status_code == 429
        assert "配额" in resp.json()["message"]
