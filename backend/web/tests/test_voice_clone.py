"""D 批（复刻接线）测试：OSS 工具 / clone 端点 / 状态刷新 / remove。"""
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import RestrictedError
from rest_framework import status

from web.models.character import Voice
from web.models.user import UserProfile


def _mp3(name='s.mp3', data=b'ID3fakeaudio'):
    """带 ID3 头的假 mp3 —— 能过 magic byte 校验（"后缀对但内容不是音频"的用例另写）"""
    return SimpleUploadedFile(name, data, content_type='audio/mpeg')


class TestOssUtil:
    def test_missing_env_raises_config_error(self, monkeypatch):
        from web.utils import oss as oss_util
        monkeypatch.delenv('OSS_BUCKET', raising=False)
        with pytest.raises(oss_util.OssConfigError) as e:
            oss_util._client()
        assert 'OSS_BUCKET' in str(e.value)

    def test_classifies_config_vs_unavailable(self):
        """把 SDK 的异常体系归一成两类（实测：SDK 的 24 个异常类没有一个继承 RuntimeError）"""
        import alibabacloud_oss_v2.exceptions as ex
        from web.utils.oss import OssConfigError, OssUnavailableError, _wrap

        def _raise(e):
            return lambda: (_ for _ in ()).throw(e)

        # 凭据错 → 配置错（500），不能当成"上游抖动"
        with pytest.raises(OssConfigError):
            _wrap(_raise(ex.CredentialsEmptyError()))
        # 客户端参数/命名校验族 → 同样是我们写错了 → 500
        # ⚠️ 这族必须带**关键字**参数构造（实测 1.2.5）：`ParamRequiredError()` 抛
        #    KeyError('field')、`BucketNameInvalidError()` 抛 KeyError('name')
        with pytest.raises(OssConfigError):
            _wrap(_raise(ex.ParamRequiredError(field='x')))
        with pytest.raises(OssConfigError):
            _wrap(_raise(ex.BucketNameInvalidError(name='bad')))
        # bucket 不存在这种带 code 的服务端错 → 也是配置错
        # ⚠️ `ServiceError` 的构造要求一串必填字段（实测依次要 status_code / code /
        #    request_id / ec …），去凑它的构造签名只会把用例写脆 ——
        #    改用 `__new__` 绕过构造再赋 code（实测可行，且 isinstance 依然成立）
        svc = ex.ServiceError.__new__(ex.ServiceError)
        svc.code = 'NoSuchBucket'
        with pytest.raises(OssConfigError):
            _wrap(_raise(svc))
        # 其它（超时/网络）→ 上游不可用（503）
        with pytest.raises(OssUnavailableError):
            _wrap(_raise(TimeoutError('slow')))
        # ⚠️ 自家异常必须原样放行：若被重新包成另一类，上面两条会有一半失效
        with pytest.raises(OssConfigError):
            _wrap(_raise(OssConfigError('x')))
        with pytest.raises(OssUnavailableError):
            _wrap(_raise(OssUnavailableError('x')))

    def test_config_error_type_names_still_exist(self):
        """软取的代价要配守卫：某个名字将来被改名/删除时，这一族会**静默**退回 503"""
        import alibabacloud_oss_v2.exceptions as ex
        from web.utils.oss import _CONFIG_ERROR_TYPE_NAMES

        for n in _CONFIG_ERROR_TYPE_NAMES:
            assert hasattr(ex, n), f'SDK 里已没有 {n}，软取的分类会静默失效'

    def test_upload_sets_object_private_and_returns_key(self, monkeypatch):
        """对象级 ACL 必须是 private —— 桶是 public-read，不能依赖桶设置"""
        from web.utils import oss as oss_util
        calls = {}

        class _FakeClient:
            def put_object(self, req):
                calls['put'] = req

            def presign(self, req, expires=None):
                calls['presign'] = req
                return type('R', (), {'url': 'https://signed.example/x'})()

            def delete_object(self, req):
                calls['del'] = req

        monkeypatch.setenv('OSS_BUCKET', 'b')
        monkeypatch.setattr(oss_util, '_client', lambda: _FakeClient())
        key = oss_util.upload_private(b'ID3bytes', 'mp3')
        assert calls['put'].acl == 'private'          # 关键断言
        assert calls['put'].key == key
        assert oss_util.presign_get(key) == 'https://signed.example/x'

    def test_delete_is_quiet_when_upstream_fails(self, monkeypatch):
        """删除失败不能抛 —— 它在 finally 里，抛出去会盖掉真正的错误"""
        from web.utils import oss as oss_util

        class _Boom:
            def delete_object(self, req):
                raise RuntimeError('boom')

        monkeypatch.setattr(oss_util, '_client', lambda: _Boom())
        oss_util.delete_object_quietly('spike/x.mp3')   # 不抛

    def test_missing_env_surfaces_as_config_error_through_upload(self, monkeypatch):
        """走**完整路径**（经 `_wrap`）而不是直接调 `_client()`

        守卫的由来：`_client()` 在 `_wrap` 的 lambda *内部*，若 `_wrap` 不放行自家异常，
        缺环境变量会被重包成 `OssUnavailableError` → 视图返 503，而 spec §7 要的是 500。
        """
        from web.utils.oss import OssConfigError, upload_private

        monkeypatch.delenv('OSS_BUCKET', raising=False)
        with pytest.raises(OssConfigError):
            upload_private(b'ID3x')


CLONE = 'web.views.create.character.voice.clone'


class TestCloneGuards:
    """参数/授权/配额的闸门 —— 这些必须在碰 OSS 之前挡住"""

    def test_missing_name_returns_400(self, auth_client):
        resp = auth_client.post('/api/create/character/voice/clone/',
                                {'file': _mp3(), 'consent': 'true'})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_consent_returns_400(self, auth_client):
        """spec §6.2.1 / §8：授权声明必须勾选，后端也要挡住（不能只靠前端）"""
        with patch(f'{CLONE}.upload_private') as up:
            resp = auth_client.post('/api/create/character/voice/clone/',
                                    {'file': _mp3(), 'name': 'n'})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert '授权' in resp.json()['message']
        assert up.call_count == 0

    def test_oversize_returns_400(self, auth_client):
        big = SimpleUploadedFile('s.mp3', b'ID3' + b'x' * (8 * 1024 * 1024),
                                 content_type='audio/mpeg')
        resp = auth_client.post('/api/create/character/voice/clone/',
                                {'file': big, 'name': 'n', 'consent': 'true'})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert '8' in resp.json()['message']          # 提示里要有上限

    def test_bad_extension_returns_400(self, auth_client):
        resp = auth_client.post('/api/create/character/voice/clone/',
                                {'file': SimpleUploadedFile('s.txt', b'x'),
                                 'name': 'n', 'consent': 'true'})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_fake_extension_rejected_by_magic_bytes(self, auth_client):
        """后缀是 mp3、内容不是音频 → 400，且不碰 OSS（spec §6.2.3 要求 magic byte）"""
        fake = SimpleUploadedFile('fake.mp3', b'this is not audio', content_type='audio/mpeg')
        with patch(f'{CLONE}.upload_private') as up:
            resp = auth_client.post('/api/create/character/voice/clone/',
                                    {'file': fake, 'name': 'n', 'consent': 'true'})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert up.call_count == 0

    def test_quota_exceeded_returns_400(self, auth_client, user_profile):
        for i in range(5):
            Voice.objects.create(name=f'v{i}', voice_id=f'q_{i}',
                                 owner=user_profile, visibility='private')
        with patch(f'{CLONE}.upload_private') as up:
            resp = auth_client.post('/api/create/character/voice/clone/',
                                    {'file': _mp3(), 'name': 'n', 'consent': 'true'})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert up.call_count == 0                     # 配额不过就不该碰 OSS


class TestCloneFlow:
    def test_success_creates_deploying_row_and_deletes_sample(self, auth_client,
                                                             user_profile):
        # ⚠️ 不用 caplog：应用 logger 有自己的 handler 且 `propagate: False`（settings.py:253），
        #    记录不会到 root，caplog 永远收不到。直接对模块 logger 打桩，断言的正是
        #    spec §8 那条契约本身——"代码把授权声明写进了日志"。
        with patch(f'{CLONE}.logger') as lg, \
             patch(f'{CLONE}.upload_private', return_value='samples/x.mp3'), \
             patch(f'{CLONE}.presign_get', return_value='https://signed/x'), \
             patch(f'{CLONE}.create_voice',
                   return_value='cosyvoice-v3-flash-new-abc') as cv, \
             patch(f'{CLONE}.delete_object_quietly') as rm:
            resp = auth_client.post('/api/create/character/voice/clone/',
                                    {'file': _mp3(), 'name': '我的音色', 'profile': '温柔',
                                     'consent': 'true'})
        assert resp.status_code == status.HTTP_200_OK
        v = Voice.objects.get(owner=user_profile)
        assert v.status == 'deploying' and v.visibility == 'private'
        assert v.voice_id == 'cosyvoice-v3-flash-new-abc'
        assert cv.call_count == 1
        assert rm.call_count == 1                     # 提交后立即删样本
        assert any('consent=true' in str(c) for c in lg.info.call_args_list), \
            f'授权声明必须落日志，实际 info 调用：{lg.info.call_args_list}'

    def test_aliyun_rejection_returns_400_and_creates_no_row(self, auth_client,
                                                            user_profile):
        from web.views.create.character.voice.clone import AliyunRejected

        with patch(f'{CLONE}.upload_private', return_value='samples/x.mp3'), \
             patch(f'{CLONE}.presign_get', return_value='https://signed/x'), \
             patch(f'{CLONE}.create_voice',
                   side_effect=AliyunRejected('400 InvalidParameter')) as cv, \
             patch(f'{CLONE}.delete_object_quietly') as rm:
            resp = auth_client.post('/api/create/character/voice/clone/',
                                    {'file': _mp3(), 'name': 'n', 'consent': 'true'})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert not Voice.objects.filter(owner=user_profile).exists()
        assert rm.call_count == 1                     # 失败路径也要删样本
        # 措辞不能断言"样本有问题"：账号配额耗尽等也会走到这里
        assert '未通过审核' not in resp.json()['message']

    def test_upstream_unavailable_returns_503(self, auth_client, user_profile):
        with patch(f'{CLONE}.upload_private', return_value='samples/x.mp3'), \
             patch(f'{CLONE}.presign_get', return_value='https://signed/x'), \
             patch(f'{CLONE}.create_voice', side_effect=TimeoutError()):
            resp = auth_client.post('/api/create/character/voice/clone/',
                                    {'file': _mp3(), 'name': 'n', 'consent': 'true'})
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert not Voice.objects.filter(owner=user_profile).exists()

    def test_oss_config_error_returns_500_not_503(self, auth_client, user_profile):
        """OSS 配置/凭据错 → 500（给运维），与"上游不可用 → 503"分成两档（spec §7）

        实测 SDK 的 24 个异常类**都不继承 RuntimeError**，所以这条走的是 `oss.py` 归一出来的
        `OssConfigError` —— 只 catch `RuntimeError` 会把"凭据错/bucket 不存在"误判成 503。
        """
        from web.utils.oss import OssConfigError

        with patch(f'{CLONE}.upload_private',
                   side_effect=OssConfigError('OSS 配置缺失: OSS_BUCKET')):
            resp = auth_client.post('/api/create/character/voice/clone/',
                                    {'file': _mp3(), 'name': 'n', 'consent': 'true'})
        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert not Voice.objects.filter(owner=user_profile).exists()

    def test_accepts_common_mp3_frame_syncs(self):
        """帧同步用**位掩码**判定而不是枚举字节对：\\xff\\xfa（带 CRC）等也要收 —— 误拒合法文件
        比误收更糟（误收最多被阿里云拒一次）"""
        from web.views.create.character.voice.clone import looks_like_audio

        for head in (b'ID3', b'\xff\xfb', b'\xff\xfa', b'\xff\xf3', b'\xff\xf2',
                     b'\xff\xe3', b'\xff\xe2'):
            assert looks_like_audio(head + b'\x00' * 16, 'mp3') is True
        assert looks_like_audio(b'this is not audio', 'mp3') is False
        assert looks_like_audio(b'RIFF' + b'\x00' * 8, 'wav') is True
        assert looks_like_audio(b'\x00\x00\x00\x20ftypM4A ', 'm4a') is True
