# P1-B2: RAG 离线评估体系 — 设计文档

> 日期：2026-06-23
> 来源：`docs/superpowers/specs/2026-06-11-next-steps-roadmap.md` P1-B2
> 状态：待实施

---

## 一、问题陈述

B1（citations 可见）、B3（距离阈值 + no-answer 防幻觉）之后，RAG 检索质量仍**无法量化**：

- 当前判断检索好坏全靠人工感觉（手动跑 shell 看 distance），**不可复现、不可回归**
- 改了 `chunk_size`、换了 embedding 模型、调了阈值，**说不清是变好还是变坏**

B2 给检索质量装一把**可量化、可回归的尺子**：用标准中文检索数据集，离线评估现有检索 pipeline（`CustomEmbeddings(text-embedding-v4)` + pgvector 余弦排序），算出 hit@1 / hit@3 / MRR@10 / NDCG@10。

### 范围界定（本期只做离线评估）

| 纳入本期 | 不纳入（拆为后续项） |
|---------|---------------------|
| 离线评估：固定数据集 + ground truth + 评分 | 在线评估：`RetrievalTrace` 加 `message_id` 关联线上对话 |

**理由**：本项目当前是 demo / 作品集，**无真实用户流量** → 在线评估现在没数据可分析，message_id 关联纯属为未来铺路（YAGNI）。离线评估现在就能产出价值（可跑、可对标 leaderboard、可回归基线）。

### 与 roadmap 的差异（集中说明）

roadmap（`2026-06-11-next-steps-roadmap.md` P1-B2）原始规格有两点与本设计不同，特此集中列出，避免认知落差：

| roadmap 原始规格 | 本设计选择 | 理由 |
|------------------|-----------|------|
| 构建 30-50 条 QA，基于系统知识库内容**手工标注** | 用**公开标准数据集** C-MTEB/CovidRetrieval（自带 qrels） | 免人工标注、可对标 leaderboard，说服力更强（详见 §2.1）。代价：评的是检索机制而非真实知识库相关性 |
| `RetrievalTrace` 增加 `message_id` / `request_id` 字段 | **本期不做**，拆为后续项 | 本项目无真实流量，在线评估暂无数据可分析，message_id 纯属为未来铺路（YAGNI，详见 §一范围界定） |

---

## 二、方案选择

### 2.1 评估数据集来源

| | 方案 A：公开标准数据集（✅ 选择） | 方案 B：自建 30-50 QA |
|---|---|---|
| **描述** | C-MTEB / CovidRetrieval（中文，~964 语料 / 949 query，自带 qrels） | 人工读真实知识库内容标注 QA + ground truth |
| **ground truth** | 数据集自带 qrels，**免标注** | 人工逐条标注，耗时 |
| **说服力** | 高——可对标 leaderboard（"text-embedding-v4 NDCG@10=X vs piccolo/stella 的 Y"） | 中——自己标的 |
| **评估对象** | 我们这套 pipeline 在标准中文语料上的检索能力 | 真实部署的 4 个文档 |

**选择 A 的理由**：本项目知识库本就是 demo 性质（4 个文档），没有"真实业务语料"；用标准集 + 对标 leaderboard 的故事更硬，且省去人工标注。**已知张力**：CovidRetrieval 是新冠新闻语料，不是 AI Friends 真实知识库，所以评估的是"检索**机制**在标准语料上好不好"，不是"用户问百炼问题能不能查到百炼文档"。但 embedding+检索算法是通用的，标准集表现能代表基础能力。

**为什么选 CovidRetrieval 而非 DuReader 全量**：DuReader-Retrieval 全量 8M passage，灌进 pgvector + embedding 成本不现实；CovidRetrieval ~964 语料，embedding 一次约 38 万 token（几毛钱），可全量评估。

### 2.2 评估时检索这一步怎么跑

| | 方案 A：抽共享检索函数（✅ 选择） | 方案 B：评估写独立 SQL | 方案 C：纯内存评估 |
|---|---|---|---|
| **描述** | 把 `graph.py` 检索核心抽成 `retrieve_chunks()`，线上工具和评估都调它 | 评估脚本自写一段 pgvector SQL | embed 后在 numpy 里算余弦，不入 DB |
| **评估对象** | 真实生产检索栈（同一份代码） | 真实 pgvector，但 SQL 是副本 | 只测 embedding 模型，**不测 pgvector** |
| **风险** | 轻度改 graph.py（有 9 个测试保护） | SQL 副本随时间**漂移**，评估悄悄失真 | 偏离 B2 初衷 |

**选择 A 的理由**：① B2 的核心价值就是"评真实生产检索栈"，A 只有一份检索核心，改了线上检索评估自动评新逻辑（可信回归基线）；② 顺带解耦过重的 `search_knowledge_base`（现在一个函数干检索+阈值过滤+格式化+写 trace）；③ 有 `test_chat_agent.py` 的 9 个 RAG 测试保护重构。B 的副本漂移会让基线不可信，C 完全没测到 pgvector 这层。

### 2.3 评估语料怎么和真实知识库隔离

| | 方案 A：专属 eval owner（✅ 选择） | 方案 B：独立评估数据库 | 方案 C：同库 + metadata 标记 |
|---|---|---|---|
| **隔离机制** | eval 语料 `owner=eval_user`，复用现成 owner 过滤 | 评估只在专用 DB 跑 | `owner=NULL` + metadata 标记 |
| **真实性** | 与真实知识库共存同表同 HNSW 索引，更接近生产难度 | 纯净语料，无干扰项，指标偏乐观 | — |
| **代价/缺陷** | 开发库常驻 ~964 chunk + 一个特殊用户 | 要配 Django 多库路由，偏重 | `owner=NULL` **必被线上召回** → 污染生产或要改生产 SQL，淘汰 |

**选择 A 的理由**：复用项目已验证的 owner 多租户隔离（系统库 `owner=NULL`、用户文档 `owner=user`），eval 语料无非"又一个 owner 的文档"，零新概念、零额外检索逻辑；同库同索引更能反映真实检索难度；最轻，一个 management command 在现有库就跑完。持久化的 chunk 还能被下次评估复用，省 embedding。

### 2.4 评估的工程形态

- **两个 management command**（项目已有 command 惯例，且评估要调真实检索栈必须在 Django context 里跑）：`rag_eval_load`（一次性导入）+ `rag_eval`（可反复跑），加一个可选 `rag_eval_cleanup`。
- **全量评估**（949 query / 964 passage）：成本可忽略，且避免"挑简单子集导致指标虚高"的质疑。
- **数据 / 报告均 git-ignored**：数据集下到 `backend/rag_eval_data/`，报告写到 `backend/rag_eval_output/` → 规避 CovidRetrieval 分发授权，仓库只存代码。
- **下载源：ModelScope**（国内网络友好，HuggingFace 直连常失败）。新依赖 `modelscope` + `pandas` 属 dev 工具，不进生产 `requirements.txt`。

---

## 三、核心设计

### 3.1 架构总览

```
ModelScope (C-MTEB/CovidRetrieval)
   corpus(~964) / queries(~949) / qrels
        │
        │  ① rag_eval_load  （下载 → 1 passage=1 chunk → embedding）
        ▼
┌──────────────────────────────────────┐
│  DocumentChunk  (owner = eval_user)    │  ← 与真实知识库共存同表同 HNSW 索引
│  metadata = {eval_id, eval_dataset}    │     靠 owner 隔离，线上永不召回
└───────────────┬──────────────────────┘
                │
        ┌───────┴────────────────────────────┐
        │  retrieve_chunks(query, top_k,       │  ← 抽出的共享检索核心
        │     user_id, include_system)          │     纯 embedding + pgvector 排序
        │  → [{chunk_id, distance, metadata}]   │     不做阈值过滤、不格式化
        └───────┬─────────────────┬────────────┘
                │                 │
       search_knowledge_base   ② rag_eval
       （线上：系统+用户）       （评估：仅 eval_user）
       自己做阈值/格式化/trace   对照 qrels 算 hit@1/hit@3/MRR@10/NDCG@10
                                 → 控制台表格 + JSON 报告(git-ignored)
```

**三个关键边界**：
1. **检索核心单一化** — `retrieve_chunks()` 是唯一检索实现，线上工具与评估都调它 → 可信回归基线。
2. **owner 隔离** — eval 语料 `owner=eval_user`；线上查"系统(NULL)+当前用户"永不带 eval_user；评估**只**查 eval_user（不带 `IS NULL`，否则真实系统库会混进评估结果）。
3. **数据不入 git** — 规避 license，仓库只存代码。

### 3.2 共享检索函数 `retrieve_chunks()`

**位置**：`backend/web/views/friend/message/chat/graph.py`

```python
def retrieve_chunks(
    query_text: str,
    top_k: int = 5,
    user_id: int | None = None,      # owner 过滤 +（track_usage 时）embedding usage 归属
    include_system: bool = True,      # 是否同时召回系统知识库（owner=NULL）
    track_usage: bool = True,         # 是否记录 embedding usage（评估传 False 避免污染生产用量）
) -> list[dict]:
    """纯检索：embedding + pgvector 余弦排序 → 结构化 top-k。
    不做阈值过滤（调用方决定），不做格式化、不写 trace。"""
```

**owner 过滤**（替换硬编码的 `owner IS NULL OR owner=%s`）：
- 线上：`include_system=True, user_id=X` → `WHERE owner_id IS NULL OR owner_id = X`
- 评估：`include_system=False, user_id=eval_user.pk` → `WHERE owner_id = eval_user_id`

**top_k 边界**：内部只做 `top_k = max(1, top_k)` 兜底（防 LIMIT 0/负数）。**不做上限钳制** —— 上限属信任边界（LLM tool call 不可信输入），由 `search_knowledge_base` 在工具层钳到 `[1, RAG_DEFAULT_MAX_RESULTS]` 后再传可信值进来；评估方传可信的 `top_k=10`（**底层若硬钳到 5，rank 6-10 命中丢失、NDCG@10/MRR@10 算错**）。

**usage 解耦**：`embed_query` 经 `embed_documents`，在 `user_id is not None` 时写 `APIUsage(api_type='embedding')`（`embeddings.py:48`）。`track_usage=False` 时内部用 `CustomEmbeddings(user_id=None)` 创建客户端（不记 usage），但 SQL owner 过滤仍用 `user_id`。线上默认 `True`（行为不变），评估传 `False` → 949 条 query 不写 949 条虚假 embedding usage。

**返回值**（结构化 dict 列表）：

```python
[{
    'chunk_id': int, 'content': str, 'chunk_index': int,
    'document_id': int | None, 'title': str | None,
    'distance': float, 'metadata': dict,   # metadata 含 eval_id / eval_dataset
}, ...]
```

两个 consumer：
- `search_knowledge_base`：遍历 → 0.5 阈值过滤 → 格式化 `[来源N:...]` + 写 trace（**对外行为/签名不变**）
- `rag_eval`：取 `metadata['eval_id']` → 对照 qrels 算命中

### 3.3 `rag_eval_load` command

**文件**：`backend/web/management/commands/rag_eval_load.py`

**职责**：下载 → 1 passage=1 chunk 导入 eval owner（幂等，`--reset` 强制重灌）

**选项**：`--reset` 清空后重灌 · `--limit N` 只导入前 N 条 passage（首次调试用，避免全量 964 embedding）

**步骤**：
1. ModelScope 下载 C-MTEB/CovidRetrieval（corpus / queries / qrels）到 `backend/rag_eval_data/`
2. 获取或创建 eval owner（`auth.User(username='__rag_eval__')` + 关联 `UserProfile`）
3. 遍历 corpus 每个 passage：
   - 幂等检查：查 `metadata__eval_id=str(corpus_id)` 是否已存在 → 跳过（**`eval_id` 统一存为 str**；PG JSONB `->>` 返回 text，corpus_id 若是 int 会 `"42" != 42` 导致幂等失效，故存取都转 str）；`--reset` 则先清空 eval owner 全部 chunk
   - **不切分**，1 passage = 1 `DocumentChunk`：`chunk_index=0`，`metadata={'eval_id': corpus_id, 'eval_dataset': 'CovidRetrieval'}`
   - `CustomEmbeddings(user_id=None)` 逐 batch（50）embedding → `bulk_create`
4. 单条 embedding 失败 → skip + 计数，不中断（fail-per-item）
5. 输出：导入 N / 跳过 M / 失败 K

### 3.4 `rag_eval` command + 指标计算

**文件**：`backend/web/management/commands/rag_eval.py`

**选项**：`--limit N` 只评估前 N 条 query（首次调试用，全量 949 条约几分钟）

**步骤**：
1. 从 cache 加载 queries + qrels → 构建 `{query_id: set([corpus_id...])}` lookup
2. 获取 eval owner
3. 遍历 949 query：`retrieve_chunks(query, top_k=10, user_id=eval_user.pk, include_system=False, track_usage=False)` → 对 top-10 每条检查 `str(metadata['eval_id']) ∈ qrels` → 记录 binary 命中向量（`track_usage=False` 避免 949 条评估 embedding 污染生产 usage）
4. 汇总指标（独立纯函数 `compute_metrics()`，便于单测）
5. 输出：控制台表格 + `backend/rag_eval_output/{timestamp}.json`

**指标**：

| 指标 | 公式 |
|------|------|
| hit@1 | top-1 命中 query 数 / 总 query 数 |
| hit@3 | top-3 至少 1 命中的 query 数 / 总 query 数 |
| MRR@10 | mean(1 / rank_of_first_hit)，无命中=0 |
| NDCG@10 | mean(DCG@10 / IDCG@10)，relevance=binary |

`DCG@k = Σᵢ relᵢ / log₂(i+1)`；IDCG 为最优排列的 DCG（binary 下 = 前 |相关| 条 rel=1 的 DCG）。

**命中判定**：1 passage=1 chunk → chunk↔passage 一一对应，**粒度天然 passage 级**。命中 = 检索回 chunk 的 `metadata['eval_id'] ∈ 该 query 的 qrels 相关集合`。

**控制台报告示意**：
```
===== RAG Evaluation =====
Dataset:   CovidRetrieval (C-MTEB)
Queries:   949    Corpus:  964
Top-K:     10     Owner:   __rag_eval__

hit@1:     XX.XX%      hit@3:    XX.XX%
MRR@10:    X.XXXX      NDCG@10:  X.XXXX

First-hit distribution:
  rank=1: NNN   rank=2: NNN   rank=3: NNN
  rank=4-10: NNN   no hit: NNN
```

### 3.5 `rag_eval_cleanup` command（可选）

**文件**：`backend/web/management/commands/rag_eval_cleanup.py`

```bash
python manage.py rag_eval_cleanup        # 删 eval owner 的全部 DocumentChunk
python manage.py rag_eval_cleanup --all  # 连 eval UserProfile + User 一起删
```

---

## 四、数据流

```
开发者: python manage.py rag_eval_load
  → ModelScope 下载 CovidRetrieval → backend/rag_eval_data/
  → get_or_create eval_user
  → 964 passage 逐条 embedding (1 passage=1 chunk, owner=eval_user)
  → DocumentChunk 写入 (metadata.eval_id=corpus_id)

开发者: python manage.py rag_eval
  → 加载 queries + qrels
  → for each query: retrieve_chunks(top_k=10, owner=eval_user only)
  → 对照 qrels 算命中
  → compute_metrics → hit@1/hit@3/MRR@10/NDCG@10
  → 控制台表格 + backend/rag_eval_output/{ts}.json
```

---

## 五、错误处理 / 边界

- **`retrieve_chunks`**：底层不吞异常（embedding/DB 异常上抛）；无命中返回 `[]`（非错误）。
- **`rag_eval_load`**：下载失败 → 报错+提示重试，非 0 退出；单条 embedding 失败 → skip+计数；重复运行 → 幂等跳过。
- **`rag_eval`**：数据未下载 → 报错"先运行 rag_eval_load"；chunk 数≠corpus 数 → warn 可 `--reset` 但继续；qrels 引用未导入的 passage → 正常计 miss；**某 query 在 qrels 中无相关项（IDCG=0）→ 排除该 query，报告标注排除数**；**单 query 检索抛异常 → per-query 容错，计失败+计数，评估跑完 949 条，报告末尾汇总失败数**。
- **合规**：数据集不入 git → 规避 CovidRetrieval 分发授权。

---

## 六、测试计划

**核心保证：重构不破现有 9 个 RAG 测试。** 那 9 个测试在 `search_knowledge_base`（@tool）层验证行为，mock 全局 `BaseDatabaseWrapper.cursor`；重构后 `search_knowledge_base` 对外行为/签名不变（cursor 仍在 `retrieve_chunks` 内），mock 路径不受函数位置影响 → 应全部照常通过。

**新增测试**：

| 测试 | 验证点 | 落点 |
|------|--------|------|
| `test_retrieve_chunks_returns_structured` | mock cursor → 返回 `list[dict]`，字段齐全 | test_chat_agent.py |
| `test_retrieve_chunks_owner_filter` | `include_system=False` 时 SQL 只含 `owner_id=%s`，无 `IS NULL` | test_chat_agent.py |
| `test_retrieve_chunks_no_threshold` | 大 distance 也返回（过滤是上层的事） | test_chat_agent.py |
| `test_retrieve_chunks_track_usage_false` | `track_usage=False` 时不调 `record_api_usage`（评估不污染 usage） | test_chat_agent.py |
| `test_compute_metrics_hit_at_k` | 命中向量 → hit@1/hit@3 算对 | test_rag_eval.py |
| `test_compute_metrics_mrr` | 命中在 rank2 → MRR=0.5 | test_rag_eval.py |
| `test_compute_metrics_ndcg` | DCG/IDCG 归一化算对 | test_rag_eval.py |
| `test_compute_metrics_no_hit` | 全 miss → 所有指标 0 | test_rag_eval.py |

**不测（YAGNI / 标 slow）**：真实 ModelScope 下载、真实 embedding API（依赖网络/真 KEY，比照 `test_tool_calling` 处理）。

---

## 七、实施清单

- [ ] `graph.py` 抽 `retrieve_chunks()`（含 `top_k=max(1,top_k)` 兜底 + `track_usage` 参数），`search_knowledge_base` 改调它（保留自身 max_results 钳制，行为不变）
- [ ] 跑现有 9 个 RAG 测试验证重构无回归
- [ ] 新增 `rag_eval_load` command（ModelScope 下载 + 1:1 导入 + 幂等(str eval_id)/reset/limit）
- [ ] 新增 `rag_eval` command（`track_usage=False` + `--limit`）+ `compute_metrics()` 纯函数
- [ ] 新增 `rag_eval_cleanup` command（可选）
- [ ] `.gitignore` 加 `backend/rag_eval_data/` 和 `backend/rag_eval_output/`
- [ ] 新增 `retrieve_chunks` 4 个测试 + `compute_metrics` 4 个测试
- [ ] 依赖说明：`modelscope` + `pandas`（dev 专用）
- [ ] 跑全量测试验证（不破现有，新增通过）
