import pytest
from django.core.exceptions import ValidationError
from django.db.models import RestrictedError

from web.models.character import Character, Voice


class TestVoiceDeleteSemantics:
    """A8 / A9：RESTRICT 的语义与守门"""

    def test_delete_referenced_voice_is_restricted(self, character, voice):
        """删被角色引用的音色 → 被拒，且角色完好（现状会被级联删掉）"""
        with pytest.raises(RestrictedError):
            voice.delete()
        assert Character.objects.filter(id=character.id).exists()

    def test_delete_unused_voice_succeeds(self, voice):
        """无人使用的音色仍可删除（clean_dirty_characters 依赖这条）"""
        vid = voice.id
        voice.delete()
        assert not Voice.objects.filter(id=vid).exists()

    def test_delete_user_with_character_does_not_raise(self, user, character):
        """A9 守门：RESTRICT 不应阻断"删用户→级联删角色"这条路径（PROTECT 会阻断）"""
        user.delete()
        assert not Character.objects.filter(id=character.id).exists()


class TestVoiceIdValidator:
    """注意：`Voice.profile` 的 default 是 `''` 却没有 blank=True，所以 full_clean() 会先因
    profile 空白报错 —— 用例必须显式给 profile 值，并断言错误挂在 voice_id 上，
    否则 pytest.raises(ValidationError) 会被 profile 的错误满足（假通过）。"""

    def test_valid_ids_pass_full_clean(self):
        """pin 用例：防止校验器过严，挡住线上三个真实标识与测试夹具"""
        for vid in ('longanyang', 'longanhuan', 'test_voice_001',
                    'cosyvoice-v3-flash-guanyin-f7af6ea4c9f947cf887c1f5f655b7d99'):
            Voice(name='x', voice_id=vid, profile='p').full_clean()

    def test_rejects_ids_with_space_or_non_ascii(self):
        for bad in ('has space', '中文音色', '-leading-dash', ''):
            with pytest.raises(ValidationError) as exc:
                Voice(name='x', voice_id=bad, profile='p').full_clean()
            assert 'voice_id' in exc.value.message_dict, \
                f'{bad!r} 应被 voice_id 拒绝，实际错误挂在：{exc.value.message_dict}'
