import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings
from rest_framework import status

SAMPLE_PATH = 'web.views.create.character.voice.sample.synthesize_once'


@pytest.fixture(autouse=True)
def _clean_sample_cache():
    """media_root 是 session 级（conftest.py:27），样音缓存会跨用例残留；
    而 voice 夹具的 voice_id 固定为 test_voice_001，缓存键也就固定 —— 必须每例清空。"""
    samples = Path(settings.MEDIA_ROOT) / 'voice_samples'
    if samples.exists():
        shutil.rmtree(samples)
    yield


class TestVoiceSample:
    """`user` 夹具本身就会创建 UserProfile（`conftest.py:58-63`），`auth_client` 依赖它，
    所以视图里的 `request.user.userprofile` 在任何用 `auth_client` 的用例里都成立
    —— 不需要额外要 `user_profile` 夹具（`test_asr.py` 的同一模式已在跑）。"""

    def test_first_request_synthesizes_and_returns_url(self, auth_client, voice):
        with patch(SAMPLE_PATH, return_value=b'ID3fakeaudio') as m:
            resp = auth_client.get('/api/create/character/voice/sample/',
                                   {'voice': voice.id})
        assert resp.status_code == status.HTTP_200_OK
        url = resp.json()['url']
        assert url.startswith(settings.MEDIA_URL)   # 生产是绝对地址
        assert 'voice_samples/' in url and url.endswith('.mp3')
        assert m.call_count == 1

    def test_second_request_hits_cache(self, auth_client, voice):
        """B2：第二次不再触发合成"""
        with patch(SAMPLE_PATH, return_value=b'ID3fakeaudio') as m:
            auth_client.get('/api/create/character/voice/sample/', {'voice': voice.id})
            resp = auth_client.get('/api/create/character/voice/sample/', {'voice': voice.id})
        assert resp.status_code == status.HTTP_200_OK
        assert m.call_count == 1

    def test_unknown_voice_returns_404(self, auth_client, db):
        resp = auth_client.get('/api/create/character/voice/sample/', {'voice': 999999})
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_synthesis_failure_returns_503(self, auth_client, voice):
        with patch(SAMPLE_PATH, side_effect=RuntimeError('boom')):
            resp = auth_client.get('/api/create/character/voice/sample/',
                                   {'voice': voice.id})
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_failure_writes_negative_cache(self, auth_client, voice):
        """B4：失败后短时间内不再打上游"""
        with patch(SAMPLE_PATH, side_effect=RuntimeError('boom')) as m:
            auth_client.get('/api/create/character/voice/sample/', {'voice': voice.id})
            resp = auth_client.get('/api/create/character/voice/sample/', {'voice': voice.id})
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert m.call_count == 1

    def test_records_usage_user_id_is_userprofile_id(self, auth_client, user, voice, db):
        """B1 的关键断言：`APIUsage.user_id` 必须是 **UserProfile.id**。

        ⚠️ 只断言 `user_id == user_profile.id` 是不够的：默认夹具下两者可能恰好相等，
        那样即使代码误传 `request.user.id`（auth User 的 PK）也会通过。所以照
        `test_asr.py:106` 的既有做法强制两个 id 分叉，让这条断言真正有区分力。
        """
        from django.contrib.auth.models import User
        from web.models.user import UserProfile

        # 先建 dummy 推进自增序列，再删掉重建测试用户的 profile → 新 id ≠ user.id
        dummy = User.objects.create_user(username='voice_sample_dummy')
        UserProfile.objects.create(user=dummy)
        UserProfile.objects.get(user=user).delete()
        new_up = UserProfile.objects.create(user=user)
        assert user.id != new_up.id, '前置条件失败：User.id 应不等于 UserProfile.id'

        with patch(SAMPLE_PATH, return_value=b'ID3fakeaudio'), \
             patch('web.views.create.character.voice.sample.record_api_usage') as rec:
            auth_client.get('/api/create/character/voice/sample/', {'voice': voice.id})
        assert rec.call_count == 1
        assert rec.call_args.kwargs['api_type'] == 'tts'
        assert rec.call_args.kwargs['update_quota'] is False
        assert rec.call_args.kwargs['user_id'] == new_up.id


class TestSampleCachePath:
    """评审 P3：缓存文件名必须受控 —— 存量/异常 voice_id 不能跑出缓存目录"""

    def test_strips_path_traversal(self):
        from web.views.create.character.voice.sample import sample_cache_path

        path = sample_cache_path('../../evil', '你好')
        assert path.parent == Path(settings.MEDIA_ROOT) / 'voice_samples'
        assert '..' not in path.name and '/' not in path.name

    def test_keeps_legal_id_intact(self):
        """pin 用例：别把合法标识也洗掉了"""
        from web.views.create.character.voice.sample import sample_cache_path

        path = sample_cache_path('longanyang', '你好')
        assert path.name.startswith('longanyang-')
        assert path.suffix == '.mp3'


class TestSynthesizeOnceTimeout:
    """B5：超时纪律的守门 —— 上游挂住时必须抛 TimeoutError，不能无限等"""

    def test_timeout_raises(self, monkeypatch):
        import asyncio

        from web.utils import tts

        async def _slow(text, voice_id):
            await asyncio.sleep(30)

        monkeypatch.setattr(tts, '_synthesize_once_async', _slow)
        monkeypatch.setattr(tts, 'TTS_TIMEOUT_SECONDS', 0.1)
        with pytest.raises(TimeoutError):      # 3.11+ 起 asyncio.TimeoutError 即内置 TimeoutError
            tts.synthesize_once('你好', 'test_voice_001')
