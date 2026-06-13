# P2-2 用户上传文档 RAG 设计文档

> 2026-05-29 | 3-5 天

## 1. 目标

用户上传个人文档（.txt/.md/.pdf），系统异步处理（文本提取 → 分块 → embedding），存入 `DocumentChunk(owner_id)`。Chat Agent 聊天时 `search_knowledge_base` 按 `owner_id` 自动召回用户个人文档 + 全局知识库。

## 2. web/documents/ 重构

### 当前问题

```
documents/
├── Bailian_Overview.md/txt       # 原始文档散落根目录
├── claude-prompting-best-practices.md
├── coding-plan-overview.md
├── lancedb_storage/              # 废弃残留
├── utils/
│   ├── insert_documents.py       # insert_documents() 和 insert_markdown_documents() 大量重复
│   ├── custom_embeddings.py      # OK
│   └── md_split_test.py          # 调试脚本，不应在正式代码中
```

### 重构后

```
documents/
├── loaders/                      # 文档加载层 — 每种文件类型一个 loader
│   ├── __init__.py
│   ├── base.py                   # AbstractLoader: load(file_path) -> list[Document]
│   ├── txt_loader.py             # TextLoader
│   ├── md_loader.py              # TextLoader → MarkdownHeaderTextSplitter → RecursiveCharacterTextSplitter
│   └── pdf_loader.py             # PyMuPDF4LLM: to_markdown() → RecursiveCharacterTextSplitter
├── services/
│   ├── __init__.py
│   ├── embeddings.py             # 从 utils/custom_embeddings.py 迁出（兼容旧导入）
│   ├── chunker.py                # 统一切分策略：RecursiveCharacterTextSplitter(chunk_size=500, overlap=50)，消除重复
│   └── insert_documents.py       # 精简：get_or_create + 调 loader + 调 chunker + 批量写 chunk
└── raw/                          # 原始文档集中存放
    ├── Bailian_Overview.md
    └── ...
```

- `loaders/base.py` 定义抽象接口：`load(file_path: str) -> list[Document]`
- 每个 loader 返回统一的 `list[Document]`，下游 `chunker.py` 无需关心来源文件类型
- `md_split_test.py` 删除（逻辑合并到 `loaders/md_loader.py`）
- `lancedb_storage/` 删除
- `custom_embeddings.py` → `services/embeddings.py`，旧路径通过 `web/documents/utils/custom_embeddings.py` 做 re-export 兼容（一个 import 行）

## 3. 新增依赖 & 配置

### 3.1 requirements.txt

```diff
+ pymupdf4llm>=0.1,<1.0
```

`pymupdf4llm` 已依赖 `PyMuPDF`，无需显式声明后者。
`RecursiveCharacterTextSplitter` 和 `MarkdownHeaderTextSplitter` 已在依赖中（langchain_text_splitters）。

### 3.2 settings.py — 文件上传大小限制

```python
# Django 默认 DATA_UPLOAD_MAX_MEMORY_SIZE = 2.5MB，必须加大
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
```

不设此值时，10MB 文件会在 API 层校验前被 Django 拒绝（413 RequestEntityTooLarge）。

## 4. 后端 API

### 4.1 上传文档 — `POST /api/document/upload/`

**同步校验（API 层，< 10ms）：**

| # | 校验项 | 方式 | 失败返回 |
|---|--------|------|---------|
| 1 | 请求中有 file | `file = request.FILES.get('file')`; `if not file: return 400` | 400 "请选择文件" |
| 2 | 非空文件 | `file.size == 0` | 400 "文件为空" |
| 3 | 文件大小 ≤ 10MB | `file.size > 10 * 1024 * 1024` | 400 "文件大小不能超过 10MB" |
| 4 | 扩展名白名单 | 白名单 `.txt` `.md` `.pdf` | 400 "不支持的文件格式，仅支持 txt/md/pdf" |
| 5 | 文件头魔数 | 读前 4 字节：PDF=`%PDF`，txt/md 非二进制（不含 null byte） | 400 "文件格式与扩展名不匹配" |

校验顺序即上表序号：先检查有无文件（否则 `.size` 抛 AttributeError → 500），再检查大小和格式。

**title 安全处理：**

```python
import os

def sanitize_title(raw_name: str) -> str:
    """从原始文件名提取安全的 title"""
    # 去掉路径分隔符，防路径遍历（../../../etc/passwd.pdf → passwd.pdf）
    basename = os.path.basename(raw_name)
    # 截断到 200 字符（DB CharField max_length）
    return basename[:200]
```

**上传逻辑：**

```python
# web/views/document/upload.py
class DocumentUploadView(APIView):
    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'message': '请选择文件'}, status=400)

        # 校验 2-5（大小、扩展名、魔数）
        # ...

        doc = UserDocument.objects.create(
            owner=request.user.userprofile,
            title=sanitize_title(file.name),
            file_url=save_to_media(file),  # media/documents/<uuid>.<ext>
            file_type=file.name.rsplit('.', 1)[-1].lower(),
            status='pending',
        )
        process_document_task.delay(doc.id)
        return Response({'id': doc.id, 'status': doc.status}, status=201)
```

文件存储到 `media/documents/<uuid>.<ext>`，前端不直接暴露文件路径。

### 4.2 文档列表 — `GET /api/document/list/`

```python
# GET /api/document/list/
# Response 200:
{
  "documents": [
    {
      "id": 1,
      "title": "AI面试准备.md",
      "file_type": "md",
      "status": "completed",      # pending | processing | completed | failed
      "error_message": "",
      "chunks_count": 12,
      "created_at": "2026-05-29T10:00:00+08:00"
    }
  ]
}
```

按 `owner=request.user.userprofile` 过滤，按 `created_at DESC` 排序，不分页。

### 4.3 删除文档 — `POST /api/document/remove/`

匹配项目中现有 `FriendRemoveView` 的模式（POST + body），避免 DELETE 请求 body 被中间件丢弃的兼容性问题。

```python
# POST /api/document/remove/
# Body: {"id": 1}
# 校验 owner == request.user.userprofile
# 级联删除 DocumentChunk + 删除 media 文件
# Response 200: {"message": "删除成功"}
```

## 5. Celery 异步任务

### `process_document_task(doc_id: int)`

位置：`web/views/document/tasks.py`（在 `web/tasks.py` 中注册导入）

```python
@app.task(max_retries=1)
def process_document_task(doc_id: int):
    try:
        doc = UserDocument.objects.get(id=doc_id)  # 已被删则 DoesNotExist → return
        doc.status = 'processing'
        doc.save()

        # 1. 选 loader → 返回 list[Document]（含 page_content + metadata）
        loader = get_loader(doc.file_type)
        documents = loader.load(doc.file_url)

        # 2. 统一切分 → 保留 metadata（如 Markdown 标题层级、PDF 页码）
        chunks = chunk_documents(documents)  # 返回 list[Document]

        # 3. 空内容检测
        if not chunks or all(not c.page_content.strip() for c in chunks):
            doc.status = 'failed'
            doc.error_message = '文档无可提取文字，可能是扫描件或空文件'
            doc.save()
            return

        # 4. 批量 embedding（仅对 page_content 向量化）
        embeddings = CustomEmbeddings()
        texts = [c.page_content for c in chunks]
        vectors = embeddings.embed_documents(texts)

        # 5. 批量写入 DocumentChunk（保留 metadata 结构信息）
        objs = [
            DocumentChunk(
                content=c.page_content, embedding=v, document=doc,
                owner=doc.owner, chunk_index=i,
                # NOTE: token_count 实际存字符数（近似），非精确 token 数。
                # 精确 token 计数需 tiktoken，当前场景字符数已足够。
                token_count=len(c.page_content),
                metadata=c.metadata,  # Markdown 标题 / PDF 页码等结构信息
            )
            for i, (c, v) in enumerate(zip(chunks, vectors))
        ]
        DocumentChunk.objects.bulk_create(objs, batch_size=50)

        doc.status = 'completed'
        doc.chunks_count = len(objs)
        doc.save()

    except UserDocument.DoesNotExist:
        return  # 文档已被用户删除，静默结束
    except Exception as exc:
        logger.exception('文档处理失败, doc_id=%d', doc_id)
        # 尝试更新状态为 failed
        try:
            doc.status = 'failed'
            doc.error_message = str(exc)[:500]
            doc.save()
        except Exception:
            pass
        # 4xx 永久故障不重试，其余重试一次
        if isinstance(exc, APIStatusError) and 400 <= exc.status_code < 500 and exc.status_code != 429:
            return
        raise process_document_task.retry(exc=exc, countdown=10)
```

### 文本编码探测

`txt_loader.py` 和 `md_loader.py` 读取文件时：

```python
def _read_with_encoding(file_path):
    for enc in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise ValueError('无法识别文件编码')
```

## 6. Chat Agent 集成

### 6.1 Tool description 更新

当前 `search_knowledge_base` 的 tool description 写死为"当用户查询'阿里云百炼'相关简介信息时"：

```python
@tool
def search_knowledge_base(query: str, state: Annotated[dict, InjectedState]) -> str:
    """
    当用户查询'阿里云百炼'相关简介信息时，调用此函数。
    ...
```

加入用户个人文档后，LLM 看到这个描述不会为用户文档查询去调用 tool。需要更新为：

```python
@tool
def search_knowledge_base(query: str, state: Annotated[dict, InjectedState]) -> str:
    """
    在知识库中检索与用户问题相关的文档内容。
    知识库包含百炼平台文档（全局）和用户上传的个人文档。
    当需要查找文档中的信息、引用资料或专业知识时，调用此函数。
    ...
```

### 6.2 SQL 查询无需修改

已有逻辑已支持 `WHERE owner_id IS NULL OR owner_id = %s`，变动范围仅 tool description 字符串。

```python
# 已有逻辑（graph.py:48）:
WHERE owner_id IS NULL OR owner_id = %s
ORDER BY embedding <=> %s::vector LIMIT 3
```

用户聊天时，Chat Agent 自动召回：全局知识库（owner=NULL）+ 该用户自己的文档（owner=user_id），各 chunk 按向量相似度排序取 top-3。

## 7. 前端设计

### 7.1 路由与导航

- 路由：`/knowledge`，`KnowledgeBase.vue`，`meta: { needLogin: true }`（匹配 `/friend/`、`/create/` 模式）
- 导航栏：`NavBar.vue` 新增"知识库"入口
- 顺便移除 `NavBar.vue` 中"聊天"的占位入口（当前 hardcoded 指向 create-index 占位），但保留 `ChatIcon.vue` 文件供后续使用

### 7.2 页面布局

```
┌─────────────────────────────────────────────────────┐
│  NavBar                                              │
├─────────────────────────────────────────────────────┤
│  知识库                                               │
│  上传你的文档，AI 将在聊天时引用其中的内容              │
├────────────────────┬────────────────────────────────┤
│                    │  文档列表                        │
│   📁 拖拽文件到此处  │                                 │
│   或点击上传       │  ┌──────────────────────────────┐│
│                    │  │ AI面试准备.md      ✓ 已完成   ││
│  支持 .txt .md .pdf │  │ 12 个片段 · 2026-05-28      ││
│  单文件 ≤ 10MB     │  │ [删除]                      ││
│                    │  └──────────────────────────────┘│
│                    │  ┌──────────────────────────────┐│
│                    │  │ 产品需求.pdf       ⏳ 处理中   ││
│                    │  │ 解析中... · 2026-05-29      ││
│                    │  └──────────────────────────────┘│
│                    │  ┌──────────────────────────────┐│
│                    │  │ 损坏文件.pdf       ✗ 失败    ││
│                    │  │ 无法识别的文件格式            ││
│                    │  │ [删除]                      ││
│                    │  └──────────────────────────────┘│
└────────────────────┴────────────────────────────────┘
```

**空状态（文档列表为空时）：**

```
┌─────────────────────────────────────────────────────┐
│  知识库                                               │
│  上传你的文档，AI 将在聊天时引用其中的内容              │
├────────────────────┬────────────────────────────────┤
│                    │                                 │
│   📁 拖拽文件到此处  │        📄 暂无文档              │
│   或点击上传       │    上传你的第一个文档吧           │
│                    │                                 │
│  支持 .txt .md .pdf │                                 │
│  单文件 ≤ 10MB     │                                 │
│                    │                                 │
└────────────────────┴────────────────────────────────┘
```

### 7.3 交互规格

**上传区：**
- 拖拽 `.txt`/`.md`/`.pdf` 文件到虚线框内 → 高亮边框
- 点击虚线框 → 弹出系统文件选择器（`accept=".txt,.md,.pdf"`）
- 文件 > 10MB → toast 警告，阻止上传
- 上传进行中 → 虚线框显示 spinner + "上传中..."，禁用拖拽/点击（防重复提交）
- 上传成功 → 文档卡片插入列表顶部，状态 `pending`，恢复上传区，自动开始轮询
- 上传失败（400）→ toast 显示后端 message，恢复上传区

**文档列表卡片：**
- 状态标签颜色：
  - `pending` — 灰色 badge（等待处理）
  - `processing` — 蓝色 badge + 旋转图标
  - `completed` — 绿色 badge + 片段数
  - `failed` — 红色 badge + 错误信息
- 删除按钮 → daisyUI modal 二次确认

**轮询逻辑（composable: `useDocumentPolling`）：**

```javascript
// 每 3 秒拉取列表
// 停止条件：列表中没有任何 pending 或 processing 状态的文档
// 兜底超时：最多轮询 120 次（6 分钟），超时后停止并 toast 提醒"部分文档处理超时，请手动刷新"
// 页面离开时 clearInterval（onUnmounted）
// 重新进入页面 → 再次拉取，按需重启轮询
```

120 次上限不是硬超时——正常文档在处理完之前就会触发停止条件。只有 Celery Worker 挂了导致文档状态永不更新时才会触发兜底。

**删除交互：**

- 点击删除 → daisyUI modal 二次确认
- 确认后 → 文档卡片立即从列表中移除（乐观更新），同时发起 POST 请求
- 后端删除失败 → toast 报错，刷新列表恢复

### 7.4 新建/修改文件

| 文件 | 操作 |
|------|------|
| `frontend/src/views/KnowledgeBase.vue` | 新建 |
| `frontend/src/components/knowledge/UploadZone.vue` | 新建 |
| `frontend/src/components/knowledge/DocumentCard.vue` | 新建 |
| `frontend/src/composables/useDocumentPolling.js` | 新建 |
| `frontend/src/js/http/api.js` | 追加 API 函数 |
| `frontend/src/router/index.js` | 追加 `/knowledge` 路由 |
| `frontend/src/components/navbar/NavBar.vue` | 追加"知识库"入口 |

## 8. 测试策略

### 8.1 现有测试更新（重构影响）

`test_document.py` 中 `TestInsertDocuments` 类直接 import `web.documents.utils.insert_documents`，重构后路径变为 `web.documents.services.insert_documents`。需要更新 import 路径，或在旧位置保留 re-export 兼容。

### 8.2 新增测试

| 测试文件 | 新增内容 |
|---------|---------|
| `test_document.py` | 追加：上传校验（大小/格式/魔数/null file）、列表过滤、删除级联、title 安全处理 |
| `test_document_processing.py`（新建） | Mock embedding API，测：txt/md/pdf 完整处理流、空文件→failed、损坏 PDF→failed、编码探测、已删除文档静默跳过、metadata 保留验证 |

## 9. 影响分析

| 模块 | 影响 |
|------|------|
| `documents/` 目录 | 重构（loaders/services 分层），旧导入兼容 |
| 新增 API | 3 个端点（upload/list/remove） |
| Celery | 1 个新任务 `process_document_task` |
| Chat Agent | 1 行改动（`search_knowledge_base` tool description 字符串更新） |
| 前端 | 新建知识库页面 + 导航栏入口 |
| 数据库 | 零 migration（`UserDocument`/`DocumentChunk` 字段已完整） |

## 10. 暂不实现

- 去重（YAGNI，后续加只需 file_hash 字段 + 唯一索引，成本低）
- 分页（个人知识库文档量小）
- 文档内容预览（后续迭代）
- 流式重试（用户手动删除后重新上传即可）
