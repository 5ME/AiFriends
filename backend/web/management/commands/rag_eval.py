"""离线评估 RAG 检索：遍历 query 调 retrieve_chunks，对照 qrels 算 hit@k/MRR/NDCG。"""
import json
import logging
import os
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand

from web.utils.rag_eval import compute_metrics, get_eval_owner
from web.views.friend.message.chat.graph import retrieve_chunks

logger = logging.getLogger(__name__)

DS_ID = 'mteb/medicalretrieval'
OUTPUT_DIR = os.path.join(settings.BASE_DIR, 'rag_eval_output')
TOP_K = 10


class Command(BaseCommand):
    help = '离线评估 RAG 检索质量（hit@1/hit@3/MRR@10/NDCG@10）'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=None,
                            help='只评估前 N 条 query（首次调试用）')

    def handle(self, *args, **options):
        limit = options['limit']

        from datasets import load_dataset
        try:
            queries = list(load_dataset(DS_ID, 'queries', split='dev'))
            qrels_raw = list(load_dataset(DS_ID, 'default', split='dev'))
        except Exception as e:
            self.stderr.write(f'加载数据集失败（HF 网络），请检查网络后重试: {e}')
            return

        # qrels：{query_id: set(corpus_id)}，统一 str；只保留 score>0 的相关项。
        # 坏行（缺字段 / score 非数值）跳过而非中断整个评估。
        qrels = {}
        for r in qrels_raw:
            qid = r.get('query-id')
            cid = r.get('corpus-id')
            if qid is None or cid is None:
                continue
            try:
                score = int(float(r.get('score', 1)))   # 容忍 "1.0" 之类浮点字符串
            except (TypeError, ValueError):
                continue
            if score > 0:
                qrels.setdefault(str(qid), set()).add(str(cid))

        eval_owner = get_eval_owner()
        if limit is not None:
            queries = queries[:limit]

        query_results = []
        excluded = failed = 0
        for q in queries:
            qid = str(q['_id'])
            relevant = qrels.get(qid)
            if not relevant:
                excluded += 1                  # qrels 中无相关项 → 排除（IDCG=0）
                continue
            try:
                # 评估检索：只查 eval owner，且不记 embedding usage
                rows = retrieve_chunks(
                    q['text'], top_k=TOP_K, user_id=eval_owner.pk,
                    include_system=False, track_usage=False,
                )
            except Exception:
                logger.exception('query 检索失败, qid=%s', qid)
                failed += 1
                continue
            hits = [str(r['metadata'].get('eval_id')) in relevant for r in rows]
            query_results.append({'hits': hits, 'num_relevant': len(relevant)})

        metrics = compute_metrics(query_results, top_k=TOP_K)
        self._report(metrics, query_results, excluded, failed, limit)

    def _report(self, metrics, query_results, excluded, failed, limit):
        evaluated = len(query_results)
        # first-hit 分布：从 hits 反推每个 query 第一个命中的 rank（无需额外数据）
        # 揭示排序信号 —— 如 hit@3 高但 first-hit 多落在 rank=4-10，说明排序仍有提升空间
        dist = {'rank=1': 0, 'rank=2': 0, 'rank=3': 0, 'rank=4-10': 0, 'no_hit': 0}
        for qr in query_results:
            rank = next((i for i, h in enumerate(qr['hits'], start=1) if h), None)
            if rank is None:
                dist['no_hit'] += 1
            elif rank <= 3:
                dist[f'rank={rank}'] += 1
            else:
                dist['rank=4-10'] += 1

        # 控制台表格
        self.stdout.write('===== RAG Evaluation (medicalretrieval, reduced corpus) =====')
        self.stdout.write(f'Evaluated: {evaluated}   Excluded(no-qrels): {excluded}   '
                          f'Failed: {failed}   Top-K: {TOP_K}')
        self.stdout.write(f"hit@1:   {metrics['hit@1']:.4f}")
        self.stdout.write(f"hit@3:   {metrics['hit@3']:.4f}")
        self.stdout.write(f"MRR@10:  {metrics['mrr@10']:.4f}")
        self.stdout.write(self.style.SUCCESS(f"NDCG@10: {metrics['ndcg@10']:.4f}"))
        self.stdout.write('First-hit distribution:')
        self.stdout.write(f"  rank=1: {dist['rank=1']}   rank=2: {dist['rank=2']}   "
                          f"rank=3: {dist['rank=3']}")
        self.stdout.write(f"  rank=4-10: {dist['rank=4-10']}   no hit: {dist['no_hit']}")

        # JSON 报告（git-ignored）
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        report = {
            'dataset': DS_ID, 'top_k': TOP_K, 'limit': limit,
            'timestamp': ts,
            'evaluated': evaluated, 'excluded': excluded, 'failed': failed,
            'metrics': metrics,
            'first_hit_distribution': dist,
        }
        path = os.path.join(OUTPUT_DIR, f'{ts}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        self.stdout.write(f'报告已写入 {path}')
