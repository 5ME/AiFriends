from io import BytesIO

import pytest
from PIL import Image
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import RestrictedError
from rest_framework import status

from web.models.character import Character, Voice


def _make_test_image(name="test.jpg"):
    """创建 1x1 白色 JPEG 的内存文件（与 test_character.py:10-16 同一写法）"""
    img = Image.new("RGB", (1, 1), color="white")
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/jpeg")


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


class TestVoiceContract:
    """A1–A4、A7：字段名统一为 voice，错误语义分档（A5/A6 依赖 C 批字段，不在此）"""

    def _payload(self, voice_value, **override):
        data = {
            'name': 'n', 'introduction': 'i', 'system_prompt': 's',
            'photo': _make_test_image('photo.jpg'),
            'background_image': _make_test_image('bg.jpg'),
        }
        if voice_value is not None:
            data['voice'] = voice_value
        data.update(override)
        return data

    def test_create_with_unknown_voice_returns_404(self, auth_client, db):
        resp = auth_client.post('/api/create/character/create/',
                                self._payload(999999))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_create_without_voice_returns_400(self, auth_client, db):
        resp = auth_client.post('/api/create/character/create/',
                                self._payload(None))
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_with_garbage_voice_returns_404(self, auth_client, db):
        """非数字 id 不能 500"""
        resp = auth_client.post('/api/create/character/create/',
                                self._payload('not-a-number'))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_update_with_unknown_voice_returns_404(self, auth_client, character):
        resp = auth_client.post('/api/create/character/update/', {
            'character_id': character.id, 'name': 'n',
            'introduction': 'i', 'system_prompt': 's', 'voice': 999999,
        })
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_update_without_voice_returns_400(self, auth_client, character):
        resp = auth_client.post('/api/create/character/update/', {
            'character_id': character.id, 'name': 'n',
            'introduction': 'i', 'system_prompt': 's',
        })
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_single_with_null_voice_returns_200(self, auth_client, character):
        """A7：角色音色为空时不再 500"""
        character.voice = None
        character.save(update_fields=['voice'])
        resp = auth_client.get('/api/create/character/get_single/',
                               {'character_id': character.id})
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()['character']['voice'] is None

    def test_get_single_returns_voice_field_name(self, auth_client, character, voice):
        resp = auth_client.get('/api/create/character/get_single/',
                               {'character_id': character.id})
        body = resp.json()['character']
        assert body['voice'] == voice.id
        assert 'voice_id' not in body

    def test_voice_list_shape(self, auth_client, voice):
        """pin 用例：钉住列表只回 id/name/profile 三个键（实现前后都应是绿的）"""
        resp = auth_client.get('/api/create/character/voice/get_list/')
        assert resp.status_code == status.HTTP_200_OK
        first = resp.json()['voices'][0]
        assert set(first) == {'id', 'name', 'profile', 'status', 'is_mine'}
