"""下载 C-MTEB/CovidRetrieval 并以 1 passage=1 chunk 导入 eval owner（离线评估语料）。"""
import logging
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from web.documents.services import CustomEmbeddings
from web.models.document import DocumentChunk
from web.utils.rag_eval import EVAL_DATASET, get_eval_owner

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(settings.BASE_DIR, 'rag_eval_data')


class Command(BaseCommand):
    help = '下载 C-MTEB/CovidRetrieval 并导入评估语料（1 passage=1 chunk）'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='导入前清空 eval owner 的全部 chunk 后重灌')
        parser.add_argument('--limit', type=int, default=None,
                            help='只导入前 N 条 passage（首次调试用）')

    def handle(self, *args, **options):
        reset = options['reset']
        limit = options['limit']

        # 1. 下载 corpus（ModelScope，国内网络友好）
        try:
            from modelscope.msdatasets import MsDataset
        except ImportError:
            self.stderr.write('缺少 modelscope，请先 pip install modelscope pandas')
            return
        try:
            corpus = MsDataset.load('C-MTEB/CovidRetrieval', subset_name='corpus',
                                    cache_dir=DATA_DIR)
        except Exception as e:
            self.stderr.write(f'ModelScope 下载失败，请检查网络后重试: {e}')
            return

        # 2. eval owner + 可选 reset
        eval_owner = get_eval_owner()
        if reset:
            deleted, _ = DocumentChunk.objects.filter(owner=eval_owner).delete()
            self.stdout.write(f'[reset] 已清空 {deleted} 条旧 eval chunk')

        # 3. 已导入的 eval_id 集合（幂等，统一 str）
        existing = set(
            DocumentChunk.objects.filter(owner=eval_owner)
            .values_list('metadata__eval_id', flat=True)
        )

        # 4. 逐条导入（1 passage=1 chunk，不切分）
        imported = skipped = failed = 0
        rows = list(corpus)
        if limit is not None:
            rows = rows[:limit]
        embedder = CustomEmbeddings(user_id=None)   # 系统导入不记 usage
        for rec in rows:
            # C-MTEB corpus schema：'_id'（passage id）、'text'（正文）、可选 'title'
            eval_id = str(rec['_id'])
            text = (rec.get('text') or '').strip()
            if not text:
                skipped += 1
                continue
            if eval_id in existing:
                skipped += 1
                continue
            try:
                vector = embedder.embed_query(text)
                DocumentChunk.objects.create(
                    content=text,
                    embedding=vector,
                    owner=eval_owner,
                    chunk_index=0,           # 1 passage=1 chunk，固定 0
                    token_count=len(text),
                    metadata={'eval_id': eval_id, 'eval_dataset': EVAL_DATASET},
                )
                imported += 1
            except Exception:
                logger.exception('导入失败, eval_id=%s', eval_id)
                failed += 1

        self.stdout.write(self.style.SUCCESS(
            f'[导入完成] 新增 {imported} / 跳过 {skipped} / 失败 {failed}'
        ))
