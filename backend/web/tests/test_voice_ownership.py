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
