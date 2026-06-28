from django.conf import settings
from django.http import Http404, HttpResponse


def index(request):
    # DEBUG=True（本地开发）读 npm build 产物 static/；
    # DEBUG=False（Docker/生产）读 collectstatic 产物 staticfiles/——
    # 容器内只挂载了 staticfiles，static/ 既被 .dockerignore 排除又未挂载。
    static_dir = settings.BASE_DIR / 'static' if settings.DEBUG else settings.STATIC_ROOT
    index_file = static_dir / 'frontend' / 'index.html'

    if not index_file.exists():
        raise Http404('前端构建文件不存在，请先执行 npm run build')

    return HttpResponse(
        index_file.read_text(encoding='utf-8'),
        content_type='text/html; charset=utf-8',
    )
