"""下载 C-MTEB/medicalretrieval 并以 1 passage=1 chunk 导入 eval owner。

仅导入 qrels 中引用的 passage（reduced corpus），避免全量 100K embedding。"""
import logging
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from web.documents.services import CustomEmbeddings
from web.models.document import DocumentChunk
from web.utils.rag_eval import EVAL_DATASET, get_eval_owner

logger = logging.getLogger(__name__)

DS_ID = 'mteb/medicalretrieval'


class Command(BaseCommand):
    help = '下载 medicalretrieval 评估语料并导入（qrels-referenced reduced corpus）'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='导入前清空 eval owner 的全部 chunk 后重灌')
        parser.add_argument('--limit', type=int, default=None,
                            help='只导入前 N 条 passage（首次调试用）')

    def handle(self, *args, **options):
        reset = options['reset']
        limit = options['limit']

        # 1. 加载 qrels → 提取 unique corpus-id（HuggingFace datasets，国际直连）
        from datasets import load_dataset
        try:
            qrels = list(load_dataset(DS_ID, 'default', split='dev'))
        except Exception as e:
            self.stderr.write(f'加载 qrels 失败，请检查网络: {e}')
            return

        relevant_ids = set()
        for r in qrels:
            try:
                if int(float(r.get('score', 1))) > 0:
                    relevant_ids.add(str(r['corpus-id']))
            except (TypeError, ValueError):
                continue

        self.stdout.write(f'qrels 涉及 {len(relevant_ids)} 个 unique passage')

        # 2. 加载 corpus（streaming 避免全量 100K 内存），仅保留 qrels 引用的 passage
        try:
            corpus = load_dataset(DS_ID, 'corpus', split='dev', streaming=True)
        except Exception as e:
            self.stderr.write(f'加载 corpus 失败: {e}')
            return

        # 3. eval owner + 可选 reset
        eval_owner = get_eval_owner()
        if reset:
            deleted, _ = DocumentChunk.objects.filter(owner=eval_owner).delete()
            self.stdout.write(f'[reset] 已清空 {deleted} 条旧 eval chunk')

        # 4. 已导入的 eval_id 集合（幂等，统一 str）
        existing = set(
            DocumentChunk.objects.filter(owner=eval_owner)
            .values_list('metadata__eval_id', flat=True)
        )

        # 5. 收集 qrels 涉及的、尚未导入的 passage
        imported = skipped = failed = 0
        to_import = []  # [(eval_id, text), ...]
        for rec in corpus:
            raw_id = rec.get('_id')
            if raw_id is None:
                continue
            eval_id = str(raw_id)
            if eval_id not in relevant_ids:
                continue  # 跳过 qrels 未引用的 passage（reduced corpus 策略）
            text = (rec.get('text') or '').strip()
            if not text or eval_id in existing:
                skipped += 1
                continue
            to_import.append((eval_id, text))
            if limit is not None and len(to_import) >= limit:
                break

        # 6. 分批 embedding（embed_documents 内部按 batch 请求）+ bulk_create
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
