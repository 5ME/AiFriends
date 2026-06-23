"""清理 RAG 评估专用数据（释放开发库空间）。"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from web.models.document import DocumentChunk
from web.models.user import UserProfile
from web.utils.rag_eval import EVAL_USERNAME


class Command(BaseCommand):
    help = '清理 RAG 评估专用 DocumentChunk（--all 连 eval 用户一起删）'

    def add_arguments(self, parser):
        parser.add_argument('--all', action='store_true',
                            help='连 eval UserProfile + User 一起删')

    def handle(self, *args, **options):
        # 非创建查找：cleanup 不应在 eval 用户不存在时反而创建它（get_or_create 的副作用）
        eval_owner = UserProfile.objects.filter(user__username=EVAL_USERNAME).first()
        if eval_owner is None:
            self.stdout.write('无 eval 数据，无需清理')
            return

        deleted, _ = DocumentChunk.objects.filter(owner=eval_owner).delete()
        self.stdout.write(self.style.SUCCESS(f'已删除 {deleted} 条 eval chunk'))

        if options['all']:
            # OneToOne：删 User 会级联删 UserProfile
            User.objects.filter(username=EVAL_USERNAME).delete()
            self.stdout.write(self.style.SUCCESS('已删除 eval 用户'))
