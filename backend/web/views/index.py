from django.conf import settings
from django.http import Http404, HttpResponse


def index(request):
    index_file = settings.BASE_DIR / 'static' / 'frontend' / 'index.html'

    if not index_file.exists():
        raise Http404('前端构建文件不存在，请先执行 npm run build')

    return HttpResponse(
        index_file.read_text(encoding='utf-8'),
        content_type='text/html; charset=utf-8',
    )
