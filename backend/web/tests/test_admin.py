"""Django Admin 注册测试"""
import pytest
from django.contrib.auth.models import User
from web.models.document import UserDocument, DocumentChunk


@pytest.fixture
def admin_client(db):
    """创建 superuser + 已登录的 Django test client"""
    User.objects.create_superuser('admin', 'admin@test.com', 'admin123')
    from django.test import Client
    client = Client()
    client.login(username='admin', password='admin123')
    return client


class TestUserDocumentAdmin:
    """UserDocument Admin 配置"""

    def test_admin_registered(self, admin_client, user_profile):
        """Admin changelist 可访问"""
        UserDocument.objects.create(
            title='admin-test', owner=user_profile,
            file_type='txt', status='completed',
        )
        resp = admin_client.get('/admin/web/userdocument/')
        assert resp.status_code == 200
        assert 'admin-test' in resp.rendered_content

    def test_search_by_title(self, admin_client, user_profile):
        """按 title 搜索能命中"""
        UserDocument.objects.create(
            title='unique-search-term', owner=user_profile,
            file_type='txt', status='completed',
        )
        resp = admin_client.get('/admin/web/userdocument/?q=unique-search-term')
        assert resp.status_code == 200
        assert 'unique-search-term' in resp.rendered_content

    def test_search_no_match(self, admin_client, user_profile):
        """搜索不匹配 → 结果为空"""
        UserDocument.objects.create(
            title='admin-test', owner=user_profile,
            file_type='txt', status='completed',
        )
        resp = admin_client.get('/admin/web/userdocument/?q=nonexistent-xyz')
        assert resp.status_code == 200
        assert 'admin-test' not in resp.rendered_content


class TestDocumentChunkAdmin:
    """DocumentChunk Admin 配置"""

    def test_admin_registered(self, admin_client, user_profile):
        """Admin changelist 可访问"""
        doc = UserDocument.objects.create(
            title='chunk-admin-test', owner=user_profile,
            file_type='txt', status='completed',
        )
        DocumentChunk.objects.create(
            content='test chunk content', embedding=[0.0] * 1024,
            document=doc, chunk_index=0,
        )
        resp = admin_client.get('/admin/web/documentchunk/')
        assert resp.status_code == 200
        # content 不在 list_display 中，但 document title 和 chunk_index 会展示
        assert 'chunk-admin-test' in resp.rendered_content
