# AI Friends 项目行动计划（2026-05-22）

> 综合 Claude + Codex 双份 Review 报告结论，结合代码实体验证结果。
> 核心原则：**先修 Bug，再补工程，后做功能。**

---

## Bug 验证结果速查

| Bug | 验证结论 | 文件 |
|-----|---------|------|
| SystemPrompt.title 用中文 label 查询，永远查不到 | ✅ **确认** | `chat/chat.py:52` `title__exact='回复'` / `memory/update.py:13` `title__exact='记忆'` → 实际存 `'reply'`/`'memory'` |
| SECRET_KEY 硬编码 | ✅ **确认** | `settings.py:23` |
| DEBUG=True / ALLOWED_HOSTS 硬编码 | ✅ **确认** | `settings.py:26-28` |
| 非作者访问角色返回 500 | ✅ **确认** | `get_single.py:41-44` / `update.py:61-64` / `remove.py:25-28` 的 `except Exception` 吞噬 `DoesNotExist` |
| README 写 SQLite/LanceDB | ✅ **确认** | 代码已迁移到 PG/pgvector，文档未更新 |

---

## 任务清单（按优先级排列）

### 🔴 P0 — 立即修复（今天/本周内）

这 4 项是"面试官一眼能看出的问题"，必须优先解决。

#### P0-1：修复 SystemPrompt.title 查询 Bug（30 分钟）⚠️ 线上功能 Bug

当前 Chat Agent 和 Memory Agent 的系统提示词查询**永远为空**，因为 model 存 `'reply'`/`'memory'`，查询用的是中文 label。

**修改文件：**
- `backend/web/views/friend/message/chat/chat.py:52`
  ```python
  # Before
  SystemPrompt.objects.filter(title__exact='回复')
  # After
  SystemPrompt.objects.filter(title=SystemPrompt.Title.REPLY)
  ```
- `backend/web/views/friend/message/memory/update.py:13`
  ```python
  # Before
  SystemPrompt.objects.filter(title__exact='记忆')
  # After
  SystemPrompt.objects.filter(title=SystemPrompt.Title.MEMORY)
  ```

**验证方式：**
- 在 Django shell 中创建一条 `SystemPrompt(title='reply', prompt='test')`，调用 `add_system_prompt()` 验证是否正确拼接
- 补充 pytest 测试：创建 SystemPrompt 数据，验证 chat.py 的 `add_system_prompt()` 和 memory/update.py 的 `update_memory()` 能正确加载

---

#### P0-2：SECRET_KEY / DEBUG / ALLOWED_HOSTS 环境变量化（30 分钟）

**修改文件：**
- `backend/.env.example` — 新增：
  ```ini
  DJANGO_SECRET_KEY=
  DJANGO_DEBUG=True
  DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
  ```
- `backend/backend/settings.py` — 改为从环境变量读取：
  ```python
  SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'change-me-in-production')
  DEBUG = os.environ.get('DJANGO_DEBUG', 'False').lower() == 'true'
  ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '127.0.0.1').split(',')
  ```
- `backend/.env` — 同步填写实际值

**注意事项：**
- 旧 SECRET_KEY 已在 git 历史中（`git log -p` 可见），需要立即变更。但变更 SECRET_KEY 会导致所有已有 refresh_token 失效 — 对个人项目影响不大，可以接受。

---

#### P0-3：修复非作者访问角色返回 500（1 小时）

`Character.objects.get(id=..., author__user=...)` 在非作者访问时抛 `DoesNotExist`，被 `except Exception` 吞噬后返回 500。应该显式处理。

**修改文件（3 个 view + 对应测试）：**

`get_single.py` / `update.py` / `remove.py` — 将 `Character.objects.get()` 改为 `filter().first()` 或 `try/except Character.DoesNotExist`：

```python
# get_single.py 示例
try:
    character = Character.objects.get(id=character_id, author__user=request.user)
except Character.DoesNotExist:
    return Response({'message': '角色不存在或无权访问'},
                    status=status.HTTP_404_NOT_FOUND)
```

**对应测试修改：**
- `test_character.py:111` → 改为 `assert resp.status_code == status.HTTP_404_NOT_FOUND`
- `test_character.py:147` → 同上
- `test_character.py:168` → 同上
- 测试注释中"按 author 过滤找不到"改为"非作者无权访问"

---

#### P0-4：README 同步更新（1.5 小时）

当前 README 与代码严重脱节，面试官第一眼就会看到过期信息。

**必须更新的内容：**
1. 后端数据库：SQLite → **PostgreSQL 17 + pgvector**
2. 向量存储：LanceDB → **pgvector**
3. 模型表：新增 `DocumentChunk`
4. 测试：新增 `python -m pytest web/tests/ -v` 命令和 49 个测试说明
5. `.env.example`：新增使用说明，列出所有必填环境变量
6. 部署文档：环境变量驱动的部署方式
7. Known Limitations：诚实地写当前限制（无 Docker、无压测、RAG 是全局知识库等）

---

### 🟡 P1 — 两周内完成（提高面试竞争力）

#### P1-1：DocumentChunk 增加元数据字段（2-3 天）

当前 `DocumentChunk` 只有 `content` / `embedding` / `created_at`，无法做用户隔离、来源引用、增量更新。

**新增字段：**
```python
class DocumentChunk(models.Model):
    content = models.TextField()
    embedding = VectorField(dimensions=1024)
    # 新增
    owner = models.ForeignKey(UserProfile, on_delete=models.CASCADE, null=True, blank=True)
    source = models.CharField(max_length=500, default='')  # 文档来源标识
    chunk_index = models.IntegerField(default=0)
    token_count = models.IntegerField(default=0)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['owner']),
            models.Index(fields=['source']),
        ]
```

**同步修改：**
- `insert_documents.py` — 改为增量插入（按 source 去重），不再全表删除
- `chat/graph.py` — `search_knowledge_base` 支持按 owner 过滤
- 新建 migration

---

#### P1-2：添加 pgvector HNSW 索引（30 分钟）

```sql
-- 在 migration 中
CREATE EXTENSION IF NOT EXISTS vector;
CREATE INDEX document_chunk_embedding_hnsw_idx
ON web_documentchunk
USING hnsw (embedding vector_cosine_ops);
```

**面试价值：** 面试官问"向量检索性能怎么保证"时，你能答出 HNSW vs IVFFlat 的权衡。

---

#### P1-3：健康检查端点 + request_id 中间件（1 天）

**新建文件：**

`backend/web/middleware/request_id.py`:
```python
import uuid
import logging

logger = logging.getLogger(__name__)

class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = str(uuid.uuid4())[:8]
        response = self.get_response(request)
        response['X-Request-ID'] = request.request_id
        return response
```

`backend/web/views/health.py`:
```python
class HealthView(APIView):
    permission_classes = []  # 无需认证

    def get(self, request):
        from django.db import connections
        db_ok = True
        try:
            connections['default'].cursor()
        except Exception:
            db_ok = False
        return Response({'status': 'ok' if db_ok else 'degraded', 'db': db_ok})
```

**注册中间件 + 路由。**

---

#### P1-4：补充 ASR / Homepage / RAG 测试（2-3 天）

当前 49 个测试覆盖约 60% 端点。优先补：

| 测试文件 | 新增内容 | 优先级 |
|---------|---------|--------|
| `test_asr.py` | ASR WebSocket mock、transcription 结果解析 | 高 |
| `test_homepage.py` | 搜索、分页、排序 | 中 |
| `test_rag.py` | CustomEmbeddings、insert_documents、pgvector 查询（需要 PG 环境） | 高 |
| `test_voice.py` | Voice CRUD 函数 | 低 |
| `test_profile.py` | Profile 更新 | 低 |

**PG 测试方案：** 在 CI/Docker 中启动 PostgreSQL 容器跑集成测试；本地开发保持 SQLite。

---

### 🟠 P2 — 一个月内完成（差异化竞争力）

#### P2-1：Celery + Redis 异步任务（2-3 天）

把以下操作改为异步：
1. **Memory Agent 摘要**（当前同步执行，阻塞聊天请求尾部）
2. **文档 embedding**（为 P2-2 做准备）
3. **自定义音色注册**

**新增依赖：** `celery` / `redis` / `django-celery-results`

**架构变化：**
```
Chat 结束写入 Message
  → Celery task: update_memory(friend_id)
  → Worker 调用 Memory Agent
  → 更新 Friend.memory
```

---

#### P2-2：用户上传文档 RAG（3-5 天）

完整链路：
```
用户上传文档
  → UserDocument(status=PENDING)
  → Celery task: process_document(doc_id)
  → 文本提取（.txt/.md/.pdf）
  → chunk 切分
  → embedding 批处理
  → 写入 DocumentChunk(owner_id, document_id, ...)
  → status=COMPLETED
  → Chat Agent search_knowledge_base 按 owner_id 过滤
```

**新增模型：** `UserDocument`（owner, title, file, file_type, status, error_message, chunks_count）

---

#### P2-3：API 限流（1 天）

```python
# settings.py
REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = ['rest_framework.throttling.UserRateThrottle']
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    'user': '1000/day',
    'chat': '20/min',
    'asr': '10/min',
    'login': '5/min',
}
```

---

#### P2-4：Docker Compose 一键启动（1-2 天）

```yaml
services:
  backend:
    build: ./backend
    depends_on: [postgres, redis]
    env_file: .env
  postgres:
    image: pgvector/pgvector:pg17
    volumes: [pgdata:/var/lib/postgresql/data]
  redis:
    image: redis:7-alpine
  frontend:
    build: ./frontend
```

**目标：** 新人 `docker-compose up` 一条命令就能跑起来。

---

### 🔵 P3 — 长期（深度能力展示）

| 功能 | 求职价值 | 预计工时 |
|------|---------|---------|
| GitHub Actions CI（pytest + frontend build） | ⭐⭐⭐ | 1 天 |
| TTS 失败降级为纯文本 | ⭐⭐⭐ | 1 天 |
| SSE 背压控制（queue.Queue maxsize） | ⭐⭐⭐ | 0.5 天 |
| AI 调用重试（tenacity） | ⭐⭐ | 0.5 天 |
| Chat Agent checkpointer 持久化 | ⭐⭐⭐ | 2 天 |
| API 文档（drf-spectacular） | ⭐⭐ | 1 天 |
| 简单压测报告（Locust） | ⭐⭐⭐ | 1 天 |
| ASGI 迁移（async 视图替代线程） | ⭐⭐ | 3-5 天 |
| Java Quota/UserDocument 辅助服务（Spring Boot） | ⭐⭐⭐⭐ | 1-2 周 |
| 用户自定义角色音色 | ⭐⭐ | 2-3 天 |
| Multi-Agent 协作 | ⭐⭐ | 3-5 天 |

---

## 执行建议

### 第 1 天

```
[ ] P0-1: 修复 SystemPrompt.title 查询（30 min）
[ ] P0-2: SECRET_KEY/DEBUG/ALLOWED_HOSTS 环境变量化（30 min）
[ ] P0-3: 修复非作者访问返回 500（1 h）
[ ] 跑一遍全量测试确认无回归（5 min）
[ ] commit + push
```

### 第 2-3 天

```
[ ] P0-4: README 更新（1.5 h）
[ ] P1-2: pgvector HNSW 索引（30 min）
[ ] P1-3: health check + request_id 中间件（1 天）
```

### 第 1-2 周

```
[ ] P1-1: DocumentChunk 元数据字段（2-3 天）
[ ] P1-4: 补充 ASR/Homepage/RAG 测试（2-3 天）
```

### 第 3-4 周

```
[ ] P2-1: Celery + Redis 异步任务（2-3 天）
[ ] P2-4: Docker Compose（1-2 天）
[ ] P2-3: API 限流（1 天）
```

### 第 5-6 周

```
[ ] P2-2: 用户上传文档 RAG（3-5 天）
[ ] P3: GitHub Actions CI（1 天）
```

---

## 完成 P0-P2 后的项目状态预估

| 维度 | 当前 | P0-P2 完成后 |
|------|------|-------------|
| 安全性 | 5/10（SECRET_KEY 硬编码） | 8/10（环境变量 + 限流） |
| 工程化 | 6/10 | 8/10（Docker + CI + Celery + 测试） |
| AI 应用深度 | 7/10 | 8.5/10（用户级 RAG + 异步任务） |
| 简历竞争力（AI 岗位） | 8/10 | 9/10 |
| 简历竞争力（Java 岗位） | 6/10 | 7/10（+Docker/CI/限流经验可迁移） |
| GitHub 吸引力 | 2/5 | 4/5 |

---

*Plan Date: 2026-05-22*
