"""SPA 入口视图 `web/views/index.py`（`/` catch-all）测试。

回归 PR #31 review P1：Docker/生产（DEBUG=False）下容器内只挂载 staticfiles/，
static/ 既被 .dockerignore 排除又未挂载，index 视图须从 STATIC_ROOT 读 index.html，
否则访问 / 返回 404 前端构建文件不存在。
"""
import pytest
from django.http import Http404
from django.test import RequestFactory, override_settings

from web.views.index import index


class TestSpaIndexView:
    """`/` → web/views/index.py 提供构建好的 SPA 入口。"""

    def test_prod_reads_staticfiles(self, tmp_path):
        """DEBUG=False 从 STATIC_ROOT（collectstatic 产物）读 index.html。"""
        frontend = tmp_path / 'frontend'
        frontend.mkdir()
        (frontend / 'index.html').write_text('<html>SPA-prod</html>', encoding='utf-8')

        with override_settings(DEBUG=False, STATIC_ROOT=tmp_path):
            response = index(RequestFactory().get('/'))

        assert response.status_code == 200
        assert 'SPA-prod' in response.content.decode()

    def test_prod_404_when_missing(self, tmp_path):
        """DEBUG=False 且 staticfiles/frontend/index.html 不存在 → 404。"""
        with override_settings(DEBUG=False, STATIC_ROOT=tmp_path):
            with pytest.raises(Http404):
                index(RequestFactory().get('/'))

    def test_dev_reads_static(self, tmp_path):
        """DEBUG=True 从 BASE_DIR/static 读（而非 STATIC_ROOT）——确认环境分支正确。

        构造一个只有 STATIC_ROOT 有 index.html 的场景：DEBUG=True 时应忽略它、
        去 BASE_DIR/static 找，找不到则 404。
        """
        frontend = tmp_path / 'frontend'
        frontend.mkdir()
        (frontend / 'index.html').write_text('<html>should-not-read</html>', encoding='utf-8')

        # DEBUG=True 时读 BASE_DIR/static，不读 STATIC_ROOT(tmp_path)；
        # 用一个不含前端产物的临时 BASE_DIR 确保走 static/ 分支并 404
        with override_settings(DEBUG=True, BASE_DIR=tmp_path / 'empty_base', STATIC_ROOT=tmp_path):
            with pytest.raises(Http404):
                index(RequestFactory().get('/'))
