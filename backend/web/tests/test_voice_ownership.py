import importlib

from django.contrib.auth.models import User

from web.models.character import Voice
from web.models.user import UserProfile


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
