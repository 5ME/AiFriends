"""seed_builtins 管理命令测试 — 内置音色 / SystemPrompt / 超级用户初始化"""
from django.contrib.auth.models import User
from django.core.management import call_command

from web.models.character import Voice
from web.models.friend import SystemPrompt


class TestSeedVoices:
    def test_creates_builtin_voices(self, db):
        call_command('seed_builtins')
        assert Voice.objects.filter(voice_id='longanyang', is_builtin=True).exists()
        assert Voice.objects.filter(voice_id='longanhuan', is_builtin=True).exists()

    def test_voice_fields_canonical(self, db):
        call_command('seed_builtins')
        v1 = Voice.objects.get(voice_id='longanyang')
        assert v1.name == '龙安洋'
        assert v1.profile == '阳光大男孩'
        v2 = Voice.objects.get(voice_id='longanhuan')
        assert v2.name == '龙安欢'
        assert v2.profile == '欢脱元气女'

    def test_rerun_does_not_duplicate(self, db):
        call_command('seed_builtins')
        call_command('seed_builtins')
        assert Voice.objects.count() == 2

    def test_updates_stale_builtin_fields(self, db):
        Voice.objects.create(name='旧名字', voice_id='longanyang', is_builtin=False)
        call_command('seed_builtins')
        v = Voice.objects.get(voice_id='longanyang')
        assert v.name == '龙安洋'
        assert v.profile == '阳光大男孩'
        assert v.is_builtin is True

    def test_does_not_touch_custom_voices(self, db):
        Voice.objects.create(name='自定义音色', voice_id='custom-1', is_builtin=False)
        call_command('seed_builtins')
        assert Voice.objects.filter(
            voice_id='custom-1', name='自定义音色', is_builtin=False
        ).exists()


class TestSeedSystemPrompts:
    def test_creates_reply_and_memory(self, db):
        call_command('seed_builtins')
        reply = SystemPrompt.objects.get(title='reply')
        memory = SystemPrompt.objects.get(title='memory')
        assert '角色定位' in reply.prompt
        assert '记忆管理模块' in memory.prompt
        assert '不要 JSON' in memory.prompt

    def test_existing_prompt_not_overwritten(self, db):
        SystemPrompt.objects.create(
            title='reply', prompt='管理员自定义内容', order_number=0,
        )
        call_command('seed_builtins')
        assert SystemPrompt.objects.get(title='reply').prompt == '管理员自定义内容'

    def test_rerun_does_not_duplicate_prompts(self, db):
        call_command('seed_builtins')
        call_command('seed_builtins')
        assert SystemPrompt.objects.count() == 2


class TestSeedSuperuser:
    def test_skipped_without_env(self, db, monkeypatch):
        monkeypatch.delenv('DJANGO_SUPERUSER_USERNAME', raising=False)
        monkeypatch.delenv('DJANGO_SUPERUSER_PASSWORD', raising=False)
        call_command('seed_builtins')
        assert not User.objects.filter(is_superuser=True).exists()

    def test_creates_superuser_with_env(self, db, monkeypatch):
        monkeypatch.setenv('DJANGO_SUPERUSER_USERNAME', 'admin')
        monkeypatch.setenv('DJANGO_SUPERUSER_PASSWORD', 'pass12345')
        monkeypatch.setenv('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
        call_command('seed_builtins')
        u = User.objects.get(username='admin')
        assert u.is_superuser and u.is_staff
        assert u.email == 'admin@example.com'
        assert u.check_password('pass12345')

    def test_existing_user_not_modified(self, db, monkeypatch):
        existing = User.objects.create_user(username='admin', password='oldpass')
        monkeypatch.setenv('DJANGO_SUPERUSER_USERNAME', 'admin')
        monkeypatch.setenv('DJANGO_SUPERUSER_PASSWORD', 'newpass')
        call_command('seed_builtins')
        existing.refresh_from_db()
        assert existing.check_password('oldpass')
        assert not existing.is_superuser

    def test_missing_one_env_var_skips(self, db, monkeypatch):
        monkeypatch.setenv('DJANGO_SUPERUSER_USERNAME', 'admin')
        monkeypatch.delenv('DJANGO_SUPERUSER_PASSWORD', raising=False)
        call_command('seed_builtins')
        assert not User.objects.filter(username='admin').exists()
