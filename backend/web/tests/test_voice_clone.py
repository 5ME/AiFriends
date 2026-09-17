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
