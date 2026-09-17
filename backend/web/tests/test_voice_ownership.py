import importlib
from io import BytesIO
from unittest.mock import patch

from PIL import Image
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from web.models.character import Voice
from web.models.user import UserProfile


def _make_test_image(name="test.jpg"):
    """创建 1x1 白色 JPEG 的内存文件（与 test_character.py / test_voice_integrity.py 同一写法）"""
    img = Image.new("RGB", (1, 1), color="white")
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/jpeg")


class TestFields:
    def test_fixture_shape(self, voice):
        """钉住夹具的形状 —— 谁把这三个显式值去掉，就会把 choices 随机性放回来"""
        assert voice.visibility == 'public'
        assert voice.status == 'ready'
        assert voice.owner is None          # 夹具不设 owner → 平台音色

    def test_field_defaults(self):
        """字段默认值 —— 这是 0024 数据迁移存在的**唯一理由**，必须钉住。

        `visibility` 默认 `private`：若有人把默认值改成 `public`，"存量置 public"那步
        就变成空操作，而 spec §4.2 与风险说明会一起失真。夹具显式传了值，
        所以默认值不会被任何其它用例覆盖到，只能在这里守。
        """
        assert Voice._meta.get_field('visibility').default == 'private'
        assert Voice._meta.get_field('status').default == 'ready'

    def test_owner_can_be_set(self, voice, user_profile):
        voice.owner = user_profile
        voice.visibility = 'private'
        voice.save()
        voice.refresh_from_db()
        assert voice.owner_id == user_profile.id

    def test_deleting_owner_deletes_voice(self, user_profile):
        """owner 是 CASCADE：用户注销时其音色随之清理（与 Character.author 一致）"""
        v = Voice.objects.create(name='v', voice_id='v_1', owner=user_profile)
        user_profile.user.delete()
        assert not Voice.objects.filter(id=v.id).exists()


class TestDataMigration:
    """C4：0024 的数据迁移必须把存量音色置为 public，否则默认值会让它们从列表里消失"""

    def test_marks_existing_rows_public(self, voice):
        from web.models.character import Voice as RealVoice

        mod = importlib.import_module(
            'web.migrations.0024_voice_owner_voice_status_voice_visibility')

        class _FakeApps:
            def get_model(self, app_label, model_name):
                return RealVoice

        RealVoice.objects.filter(pk=voice.pk).update(visibility='private')
        mod.mark_existing_public(_FakeApps(), None)
        voice.refresh_from_db()
        assert voice.visibility == 'public'


class TestVisibilityRule:
    """C1 / C3：列表只回公开或自己的，且 is_mine 正确"""

    def _make(self, user_profile, voice_id, **kw):
        return Voice.objects.create(name=voice_id, voice_id=voice_id,
                                    owner=user_profile, **kw)

    def test_list_returns_public_and_own_only(self, auth_client, user_profile,
                                             other_user, voice):
        mine = self._make(user_profile, 'mine_1', visibility='private')
        # other_user 夹具自身就创建了 UserProfile（conftest.py:113-118）
        public = self._make(other_user.userprofile, 'publ_1', visibility='public')
        others_private = Voice.objects.create(
            name='op', voice_id='op_1',
            owner=UserProfile.objects.create(user=User.objects.create_user('third')),
            visibility='private')

        resp = auth_client.get('/api/create/character/voice/get_list/')
        ids = {v['id'] for v in resp.json()['voices']}
        assert voice.id in ids                 # 夹具是 public
        assert mine.id in ids                  # 自己的私有音色可见
        assert public.id in ids                # 别人的公开音色可见
        assert others_private.id not in ids    # 别人的私有音色不可见

    def test_is_mine_flag(self, auth_client, user_profile, voice):
        mine = self._make(user_profile, 'mine_2', visibility='private')
        resp = auth_client.get('/api/create/character/voice/get_list/')
        by_id = {v['id']: v for v in resp.json()['voices']}
        assert by_id[mine.id]['is_mine'] is True
        assert by_id[voice.id]['is_mine'] is False      # 平台音色

    def test_status_exposed(self, auth_client, user_profile, voice):
        rejected = self._make(user_profile, 'rej_1', status='rejected')
        resp = auth_client.get('/api/create/character/voice/get_list/')
        by_id = {v['id']: v for v in resp.json()['voices']}
        assert by_id[rejected.id]['status'] == 'rejected'

    def test_get_single_voices_filtered(self, auth_client, character, voice):
        """详情页的音色下拉也走同一条可见性规则"""
        Voice.objects.create(name='op2', voice_id='op_2',
                             owner=UserProfile.objects.create(
                                 user=User.objects.create_user('fourth')),
                             visibility='private')
        resp = auth_client.get('/api/create/character/get_single/',
                               {'character_id': character.id})
        names = {v['name'] for v in resp.json()['voices']}
        assert 'op2' not in names


class TestSelectionGuards:
    """A5 / A6 / B3 后半：选角与试听都要过可见性与可用性两道闸"""

    def _other_private(self):
        other = UserProfile.objects.create(user=User.objects.create_user('other2'))
        return Voice.objects.create(name='私有', voice_id='priv_1',
                                    owner=other, visibility='private')

    def _payload(self, voice_value):
        """create 的完整必填载荷。校验顺序是 name→introduction→system_prompt→
        photo→background_image→voice（`create.py:27-45`），只传 voice 会先栽在 name 上返回 400。"""
        return {
            'name': 'n', 'introduction': 'i', 'system_prompt': 's',
            'voice': voice_value,
            'photo': _make_test_image('photo.jpg'),
            'background_image': _make_test_image('bg.jpg'),
        }

    def test_create_with_others_private_voice_returns_404(self, auth_client):
        """A6：404，且 message 与"不存在"逐字相同（否则 404 成了存在性探测器）"""
        v = self._other_private()
        r1 = auth_client.post('/api/create/character/create/', self._payload(v.id))
        r2 = auth_client.post('/api/create/character/create/', self._payload(999999))
        assert r1.status_code == status.HTTP_404_NOT_FOUND
        assert r2.status_code == status.HTTP_404_NOT_FOUND
        assert r1.json()['message'] == r2.json()['message']

    def test_update_with_others_private_voice_returns_404(self, auth_client, character):
        v = self._other_private()
        resp = auth_client.post('/api/create/character/update/', {
            'character_id': character.id, 'name': 'n', 'introduction': 'i',
            'system_prompt': 's', 'voice': v.id})
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_update_with_not_ready_voice_returns_400(self, auth_client, character,
                                                     voice):
        """A5：可见但没就绪 → 400（与 404 区分开，用户能知道该等还是该换）"""
        voice.status = 'deploying'
        voice.save(update_fields=['status'])
        resp = auth_client.post('/api/create/character/update/', {
            'character_id': character.id, 'name': 'n', 'introduction': 'i',
            'system_prompt': 's', 'voice': voice.id})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_sample_of_others_private_voice_returns_404(self, auth_client):
        v = self._other_private()
        resp = auth_client.get('/api/create/character/voice/sample/', {'voice': v.id})
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_sample_of_not_ready_voice_returns_400(self, auth_client, voice):
        """B3 后半：没就绪就不该去打阿里云（用 mock 断言零调用）"""
        voice.status = 'rejected'
        voice.save(update_fields=['status'])
        with patch('web.views.create.character.voice.sample.synthesize_once') as m:
            resp = auth_client.get('/api/create/character/voice/sample/',
                                   {'voice': voice.id})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert m.call_count == 0
