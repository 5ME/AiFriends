"""RAG 离线评估的共享工具：指标计算 + 评估专用 owner 管理。"""
import math

from django.contrib.auth.models import User

from web.models.user import UserProfile

# 评估专用账号 / 数据集标识（与真实用户、真实知识库隔离）
EVAL_USERNAME = '__rag_eval__'
EVAL_DATASET = 'CovidRetrieval'


def get_eval_owner() -> UserProfile:
    """获取或创建 RAG 评估专用 UserProfile。

    评估语料以此 owner 写入 DocumentChunk，靠 owner 过滤与真实知识库隔离：
    线上检索查 `owner IS NULL OR owner=真实用户`，永不命中此 owner。
    """
    user, _ = User.objects.get_or_create(
        username=EVAL_USERNAME,
        defaults={'is_active': False},   # 评估账号不可登录
    )
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def compute_metrics(query_results: list[dict], top_k: int = 10) -> dict:
    """根据每个 query 的命中情况汇总检索指标。

    :param query_results: 每项 {'hits': list[bool], 'num_relevant': int}
        hits         —— top-k 各位置是否命中相关 passage（按检索排序，True=命中）
        num_relevant —— 该 query 在 qrels 中的相关 passage 总数（用于 IDCG 归一化）
        注：无相关项（num_relevant==0）的 query 应由调用方提前排除，不传入此函数。
    :return: {'hit@1', 'hit@3', 'mrr@10', 'ndcg@10'}
    """
    n = len(query_results)
    if n == 0:
        return {'hit@1': 0.0, 'hit@3': 0.0, 'mrr@10': 0.0, 'ndcg@10': 0.0}

    hit1 = hit3 = 0
    mrr_sum = ndcg_sum = 0.0
    for qr in query_results:
        hits = qr['hits'][:top_k]
        num_rel = qr['num_relevant']

        if hits and hits[0]:
            hit1 += 1
        if any(hits[:3]):
            hit3 += 1

        # MRR：第一个命中位置的倒数（无命中贡献 0）
        for rank, hit in enumerate(hits, start=1):
            if hit:
                mrr_sum += 1.0 / rank
                break

        # NDCG@k（binary relevance）：DCG / IDCG
        # IDCG 取「理想排序」——前 min(num_rel, top_k) 个全命中
        dcg = sum(1.0 / math.log2(i + 2) for i, hit in enumerate(hits) if hit)
        ideal_n = min(num_rel, top_k)
        idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_n))
        ndcg_sum += (dcg / idcg) if idcg > 0 else 0.0

    return {
        'hit@1': hit1 / n,
        'hit@3': hit3 / n,
        'mrr@10': mrr_sum / n,
        'ndcg@10': ndcg_sum / n,
    }
