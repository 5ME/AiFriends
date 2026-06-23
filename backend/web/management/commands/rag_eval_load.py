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

        # 4. 收集待导入（过滤缺 _id / 空文本 / 已存在），再分批 embedding 写入
        imported = skipped = failed = 0
        rows = list(corpus)
        if limit is not None:
            rows = rows[:limit]

        to_import = []  # [(eval_id, text), ...]
        for rec in rows:
            raw_id = rec.get('_id')
            if raw_id is None:          # 防御缺字段记录，跳过而非中断
                skipped += 1
                continue
            eval_id = str(raw_id)
            text = (rec.get('text') or '').strip()
            if not text or eval_id in existing:
                skipped += 1
                continue
            to_import.append((eval_id, text))

        # 分批 embedding（embed_documents 内部按 batch 请求）+ bulk_create，
        # 复用 insert_documents 的批量模式，避免逐条 round trip
        embedder = CustomEmbeddings(user_id=None)   # 系统导入不记 usage
        BATCH = 50
        for i in range(0, len(to_import), BATCH):
            batch = to_import[i:i + BATCH]
            texts = [t for _, t in batch]
            try:
                vectors = embedder.embed_documents(texts)
            except Exception:
                logger.exception('批 embedding 失败, batch_start=%d', i)
                failed += len(batch)
                continue
            objs = [
                DocumentChunk(
                    content=t, embedding=v, owner=eval_owner,
                    chunk_index=0, token_count=len(t),
                    metadata={'eval_id': eid, 'eval_dataset': EVAL_DATASET},
                )
                for (eid, t), v in zip(batch, vectors)
            ]
            DocumentChunk.objects.bulk_create(objs, batch_size=50)
            imported += len(objs)

        self.stdout.write(self.style.SUCCESS(
            f'[导入完成] 新增 {imported} / 跳过 {skipped} / 失败 {failed}'
        ))
