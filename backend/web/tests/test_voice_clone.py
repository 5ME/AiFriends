"""D 批（复刻接线）测试：OSS 工具 / clone 端点 / 状态刷新 / remove。"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import RestrictedError
from django.utils import timezone
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

    def test_unwraps_operation_error_before_classifying(self):
        """SDK 在请求边界把所有异常包成 `OperationError`（`_client.py:332`），
        分类前必须先 `unwrap()` —— 否则类型白名单永远不命中（等于死代码）。

        实测三种情形的内层：桶不存在 → ServiceError(NoSuchBucket)；桶名非法 →
        BucketNameInvalidError；网络不可达 → RequestError。
        """
        import alibabacloud_oss_v2.exceptions as ex
        from web.utils.oss import OssConfigError, OssUnavailableError, _wrap

        def _new(cls, **attrs):
            # 这些异常类的构造要一串 kwarg（实测），用 __new__ 绕开，让用例只关心分类
            obj = cls.__new__(cls)
            for k, v in attrs.items():
                setattr(obj, k, v)
            return obj

        def _wrapped(inner):
            # `exceptions.py:157-169`：OperationError 用 `_error` 存内层、`unwrap()` 取出来
            op = _new(ex.OperationError, _error=inner)
            assert op.unwrap() is inner, 'SDK 的 unwrap 语义变了，本用例的前提失效'
            return lambda: (_ for _ in ()).throw(op)

        svc = _new(ex.ServiceError, code='NoSuchBucket')
        with pytest.raises(OssConfigError):
            _wrap(_wrapped(svc))                       # 桶不存在 → 500（配置错）

        with pytest.raises(OssConfigError):
            _wrap(_wrapped(_new(ex.BucketNameInvalidError)))   # 桶名非法 → 500（配置错）

        with pytest.raises(OssUnavailableError):
            _wrap(_wrapped(_new(ex.RequestError)))     # 网络不可达 → 503（上游错）

    def test_error_message_carries_inner_type(self):
        """日志要带**内层**类型：外层永远是 OperationError，光看它没有诊断价值"""
        import alibabacloud_oss_v2.exceptions as ex
        from web.utils.oss import OssUnavailableError, _wrap

        op = ex.OperationError.__new__(ex.OperationError)
        op._error = ex.RequestError.__new__(ex.RequestError)
        with pytest.raises(OssUnavailableError) as e:
            _wrap(lambda: (_ for _ in ()).throw(op))
        assert 'RequestError' in str(e.value)

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


REFRESH = 'web.tasks.voice_status.query_status'


class TestStatusRefresh:
    """Beat 任务：每 5 分钟扫一批 deploying 行，用 query_voice 回写状态"""

    def test_ok_becomes_ready(self, db):
        from web.tasks.voice_status import refresh_deploying_voices

        v = Voice.objects.create(name='v', voice_id='ok_1', status='deploying')
        with patch(REFRESH, return_value='OK'):
            refresh_deploying_voices()
        v.refresh_from_db()
        assert v.status == 'ready'

    def test_undeployed_becomes_rejected(self, db):
        from web.tasks.voice_status import refresh_deploying_voices

        v = Voice.objects.create(name='v', voice_id='un_1', status='deploying')
        with patch(REFRESH, return_value='UNDEPLOYED'):
            refresh_deploying_voices()
        v.refresh_from_db()
        assert v.status == 'rejected'

    def test_still_deploying_keeps_state(self, db):
        from web.tasks.voice_status import refresh_deploying_voices

        v = Voice.objects.create(name='v', voice_id='dg_1', status='deploying')
        with patch(REFRESH, return_value='DEPLOYING'):
            refresh_deploying_voices()
        v.refresh_from_db()
        assert v.status == 'deploying'

    def test_skips_rows_older_than_24h(self, db):
        """24 小时窗口之外的不再查询（避免长期 deploying 的行被无限重试）"""
        from web.tasks.voice_status import refresh_deploying_voices

        v = Voice.objects.create(name='v', voice_id='old_1', status='deploying')
        Voice.objects.filter(pk=v.pk).update(
            created_at=timezone.now() - timedelta(hours=25))
        with patch(REFRESH) as q:
            refresh_deploying_voices()
        assert q.call_count == 0

    def test_one_failure_does_not_block_others(self, db):
        """单条抛异常不能影响其余行，且失败的那条 fail-open 保持原状态"""
        from web.tasks.voice_status import refresh_deploying_voices

        a = Voice.objects.create(name='a', voice_id='f_1', status='deploying')
        b = Voice.objects.create(name='b', voice_id='f_2', status='deploying')
        with patch(REFRESH, side_effect=[RuntimeError('boom'), 'OK']):
            refresh_deploying_voices()
        b.refresh_from_db()
        assert b.status == 'ready'                    # 后面的照常处理
        a.refresh_from_db()
        assert a.status == 'deploying'                # fail-open

    def test_batch_limit(self, db):
        """单轮上限 20 条，避免占满单并发 worker"""
        from web.tasks.voice_status import refresh_deploying_voices

        for i in range(25):
            Voice.objects.create(name=f'v{i}', voice_id=f'b_{i}', status='deploying')
        with patch(REFRESH, return_value='OK') as q:
            refresh_deploying_voices()
        assert q.call_count == 20

    def test_ready_rows_are_not_queried(self, db):
        """只扫 deploying —— ready / rejected 的行不该被反复查询"""
        from web.tasks.voice_status import refresh_deploying_voices

        Voice.objects.create(name='r', voice_id='rd_1', status='ready')
        Voice.objects.create(name='j', voice_id='rj_1', status='rejected')
        with patch(REFRESH) as q:
            refresh_deploying_voices()
        assert q.call_count == 0


REMOVE = 'web.views.create.character.voice.remove'


class TestRemoveVoice:
    """删除音色：可见性 → 引用检查 → 删阿里云 → 删本地行（spec §7 只有两档）"""

    def test_removes_own_unused_voice_and_calls_aliyun(self, auth_client, user_profile):
        v = Voice.objects.create(name='m', voice_id='rm_1', owner=user_profile,
                                 visibility='private')
        with patch(f'{REMOVE}.delete_voice') as dv:
            resp = auth_client.post('/api/create/character/voice/remove/', {'voice': v.id})
        assert resp.status_code == status.HTTP_200_OK
        assert not Voice.objects.filter(id=v.id).exists()
        assert dv.call_count == 1

    def test_voice_in_use_returns_400_without_calling_aliyun(self, auth_client,
                                                             user_profile, character):
        """被自己的角色引用 → 400，且本地就能判定、不该白跑一趟上游

        注意要用**自己的**音色：`character` 夹具默认引用的是平台音色，而那条路径会先被
        归属检查挡成 404（见 `test_platform_voice_cannot_be_removed`），测不到引用检查。
        """
        v = Voice.objects.create(name='在用', voice_id='in_use_1', owner=user_profile,
                                 visibility='private')
        character.voice = v
        character.save(update_fields=['voice'])
        with patch(f'{REMOVE}.delete_voice') as dv:
            resp = auth_client.post('/api/create/character/voice/remove/', {'voice': v.id})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert '角色' in resp.json()['message']
        assert dv.call_count == 0            # 本地就能判定，不该白跑一趟上游

    def test_others_voice_returns_404_same_message(self, auth_client):
        """不可见与不存在必须回同一个 message（防存在性探测）"""
        other = UserProfile.objects.create(user=User.objects.create_user('rm_other'))
        v = Voice.objects.create(name='o', voice_id='rm_2', owner=other,
                                 visibility='private')
        r1 = auth_client.post('/api/create/character/voice/remove/', {'voice': v.id})
        r2 = auth_client.post('/api/create/character/voice/remove/', {'voice': 999999})
        assert r1.status_code == r2.status_code == status.HTTP_404_NOT_FOUND
        assert r1.json()['message'] == r2.json()['message']

    def test_aliyun_failure_keeps_row(self, auth_client, user_profile):
        """上游失败/超时 → 503 且**保留本地行**（保住 voice_id 以便重试）"""
        v = Voice.objects.create(name='m', voice_id='rm_3', owner=user_profile,
                                 visibility='private')
        with patch(f'{REMOVE}.delete_voice', side_effect=RuntimeError('boom')):
            resp = auth_client.post('/api/create/character/voice/remove/', {'voice': v.id})
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert Voice.objects.filter(id=v.id).exists()

    def test_aliyun_not_found_still_deletes_local_row(self, auth_client, user_profile):
        """阿里云侧已被 1 年规则清理掉的音色，本地删除应当成功（Task 1 实测的真实形状）"""
        from web.views.create.character.voice.remove import AliyunNotFound

        v = Voice.objects.create(name='m', voice_id='rm_4', owner=user_profile,
                                 visibility='private')
        with patch(f'{REMOVE}.delete_voice', side_effect=AliyunNotFound()):
            resp = auth_client.post('/api/create/character/voice/remove/', {'voice': v.id})
        assert resp.status_code == status.HTTP_200_OK
        assert not Voice.objects.filter(id=v.id).exists()

    def test_platform_voice_cannot_be_removed(self, auth_client, voice):
        """平台音色（owner=None）不该被任何用户删掉 —— spec §5：只能删**自己的**音色

        守卫必须是"归属"而不是"可见性"：可见性对平台音色恒为真（`public`），
        拿可见性当准入条件 = 任何登录用户都能删龙安洋 / 龙安欢 / 管理员手工录入的音色
        （前两者能被 seed 补回来，手工录入的那个不能）。
        """
        with patch(f'{REMOVE}.delete_voice') as dv:
            resp = auth_client.post('/api/create/character/voice/remove/',
                                    {'voice': voice.id})
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert Voice.objects.filter(id=voice.id).exists()   # 本地行必须还在
        assert dv.call_count == 0                           # 更不该去动阿里云侧

    def test_others_public_voice_cannot_be_removed(self, auth_client):
        """别人的**公开**音色同样不可删（二期开放共享后这条会变得更要紧）"""
        other = UserProfile.objects.create(user=User.objects.create_user('rm_pub'))
        v = Voice.objects.create(name='公开的', voice_id='rm_pub_1', owner=other,
                                 visibility='public')
        with patch(f'{REMOVE}.delete_voice') as dv:
            resp = auth_client.post('/api/create/character/voice/remove/', {'voice': v.id})
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert Voice.objects.filter(id=v.id).exists()
        assert dv.call_count == 0

    def test_own_voice_is_still_removable(self, auth_client, user_profile):
        """pin 用例：归属校验不能把"删自己的"也一起挡掉"""
        v = Voice.objects.create(name='我的', voice_id='rm_own_1', owner=user_profile,
                                 visibility='private')
        with patch(f'{REMOVE}.delete_voice'):
            resp = auth_client.post('/api/create/character/voice/remove/', {'voice': v.id})
        assert resp.status_code == status.HTTP_200_OK
        assert not Voice.objects.filter(id=v.id).exists()

    def test_restricted_race_returns_400_not_500(self, auth_client, user_profile):
        """预检查与真正删除之间的竞态：这中间新建了一个用它的角色 → 被 RESTRICT 拒绝

        不补这层兜底，`RestrictedError` 会漏到最外面变成 500（spec §7 明确不许）。
        """
        v = Voice.objects.create(name='m', voice_id='rm_5', owner=user_profile,
                                 visibility='private')
        with patch(f'{REMOVE}.delete_voice'), \
             patch.object(Voice, 'delete',
                          side_effect=RestrictedError('still referenced', [])):
            resp = auth_client.post('/api/create/character/voice/remove/', {'voice': v.id})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert '角色' in resp.json()['message']


class TestCleanCommandGuard:
    """`clean_dirty_characters --all` 会删音色和用户：D 批之后它从"清测试残留"
    变成"能删真实用户数据"，所以生产（DEBUG=False）下必须拒绝执行。"""

    def test_all_refused_when_not_debug(self, settings):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        settings.DEBUG = False
        with pytest.raises(CommandError) as e:
            call_command('clean_dirty_characters', '--all')
        assert 'DEBUG' in str(e.value) or '生产' in str(e.value)

    def test_all_allowed_when_debug(self, settings, db):
        from django.core.management import call_command

        settings.DEBUG = True
        call_command('clean_dirty_characters', '--all')      # 不抛
