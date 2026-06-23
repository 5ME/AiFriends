import math
import pytest


class TestComputeMetrics:
    """RAG 检索指标计算 —— 纯函数，不碰 DB"""

    def test_compute_metrics_hit_at_k(self):
        from web.utils.rag_eval import compute_metrics
        # query1: top-1 命中；query2: rank3 命中
        results = [
            {'hits': [True, False, False], 'num_relevant': 1},
            {'hits': [False, False, True], 'num_relevant': 1},
        ]
        m = compute_metrics(results, top_k=10)
        assert m['hit@1'] == 0.5     # 只有 query1 top-1 命中
        assert m['hit@3'] == 1.0     # 两个 query 都在 top-3 命中

    def test_compute_metrics_mrr(self):
        from web.utils.rag_eval import compute_metrics
        # 命中在 rank 2 → RR = 1/2
        results = [{'hits': [False, True, False], 'num_relevant': 1}]
        m = compute_metrics(results, top_k=10)
        assert m['mrr@10'] == pytest.approx(0.5)

    def test_compute_metrics_ndcg(self):
        from web.utils.rag_eval import compute_metrics
        # 单相关、命中在 rank 2 → DCG=1/log2(3)，IDCG=1/log2(2)=1
        results = [{'hits': [False, True], 'num_relevant': 1}]
        m = compute_metrics(results, top_k=10)
        expected = (1.0 / math.log2(3)) / (1.0 / math.log2(2))
        assert m['ndcg@10'] == pytest.approx(expected)

    def test_compute_metrics_no_hit(self):
        from web.utils.rag_eval import compute_metrics
        results = [{'hits': [False] * 10, 'num_relevant': 1}]
        m = compute_metrics(results, top_k=10)
        assert m['hit@1'] == 0.0
        assert m['hit@3'] == 0.0
        assert m['mrr@10'] == 0.0
        assert m['ndcg@10'] == 0.0
