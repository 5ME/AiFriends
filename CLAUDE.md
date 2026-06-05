# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Friends — a full-stack web app where users create AI characters ("friends") and chat with them. Supports text + voice input/output, long-term memory summarization, and RAG-based knowledge retrieval.

- **Backend:** Django 6.0 + Django REST Framework + JWT auth (PostgreSQL 17 + pgvector 0.8)
- **Frontend:** Vue 3 (Composition API) + Vite 7 + Pinia + Vue Router 5 + Tailwind CSS 4 + daisyUI 5
- **AI:** Alibaba DashScope (Qwen models) via OpenAI-compatible API. LangChain/LangGraph for orchestration. pgvector for vector storage.
- **Voice:** DashScope TTS (WebSocket streaming) + ASR (WebSocket). Browser-side VAD via `@ricky0123/vad-web` (Silero VAD on ONNX).

## Commands

### Backend (Python/Django)

Uses conda environment at `D:\MyWork\Miniconda3\envs\py312`. Activate with `conda activate py312` before running commands.

```bash
cd backend
pip install -r ../requirements.txt      # requirements.txt 在项目根目录
# DEBUG / SECRET_KEY 等通过 .env 环境变量控制，无需手动改 settings.py
python manage.py runserver              # Dev server on :8000
python -m pytest web/tests/ -v         # Run all backend tests (~99 tests)
# PostgreSQL & Redis: Docker Compose 一键启动（见下方 Infrastructure）
# .env 模板: cp .env.example .env
python manage.py clean_dirty_characters --all  # Clean test residue data
# 部署到云服务器时 DEBUG = False
python manage.py collectstatic          # Collect static files for production
```

### Frontend (Node/Vue/Vite)

```bash
cd frontend
npm install
npm run dev         # Vite dev server with HMR on :5173
npm run build       # Production build → ../backend/static/frontend/
npm run preview     # Preview production build locally
```

### Infrastructure

**Docker Compose** (`docker-compose.yml` at project root):

```bash
wsl docker compose up -d   # 启动 PostgreSQL 17 + pgvector + Redis 7
```

**Celery Worker:**

```bash
cd backend
celery -A backend worker --loglevel=info --pool=solo
```

### Production Deployment

1. `cd frontend && npm run build`（自动使用 cloud 模式）
2. `cd backend && python manage.py collectstatic`
3. Start gunicorn: `gunicorn --workers 3 --bind unix:gunicorn.sock backend.wsgi:application`
4. Start Celery Worker: `celery -A backend worker --loglevel=info --pool=solo`
5. Nginx reverse-proxies to the gunicorn socket (see `服务器部署.md` for full Nginx config)

**前端 platform 自动切换：**

| 场景 | 命令 | 使用的 API 地址 |
|------|------|----------------|
| 开发热更新 | `npm run dev` | `http://127.0.0.1:8000` |
| 本地打包测试 | `$env:VITE_PLATFORM='django'; npm run build` | `http://127.0.0.1:8000` |
| 生产部署 | `npm run build` | `VITE_CLOUD_BASE` 或 `https://115.190.245.146` |

## Architecture

### Testing (pytest)

- Tests in `web/tests/`, run with `python -m pytest web/tests/ -v` (~99 tests)
- `conftest.py` provides global fixtures: `api_client`, `user`, `auth_client`, `character`, `friend`, etc.
- `media_root` fixture (autouse, session-scoped) redirects test uploads to a temp directory — test files never touch real `media/`
- Tests use `model_bakery` (baker.make) + `pytest-django` transaction rollback
- **Dual-DB strategy:** tests run on PostgreSQL `aifriends_test` database (auto-detected via `sys.argv`), separated from the development `aifriends` database. Avoids polluting development data during tests.

### How the stacks connect

The frontend is built into `backend/static/frontend/`. Django serves the SPA via a catch-all route: `web/views/index.py` renders `templates/index.html`, which loads the Vite-built assets. All API routes live under `/api/` in `backend/web/urls.py`.

### Environment / platform modes

`frontend/src/js/config/config.js` 根据 Vite MODE 和 `VITE_PLATFORM` 环境变量自动切换：

| Mode | HTTP base | 触发方式 |
|------|-----------|---------|
| `vue` | `http://127.0.0.1:8000` | `VITE_PLATFORM=vue npm run dev` |
| `django` | `http://127.0.0.1:8000` | `npm run dev`（默认）|
| `cloud` | `VITE_CLOUD_BASE` 或 `https://115.190.245.146` | `npm run build`（默认）|

不再需要手动改 `platform` 变量。`npm run dev` 和 `npm run build` 会自动选择合适的模式。

### JWT auth flow

- Login/register returns `access_token` (2h TTL) in response body + `refresh_token` (7d TTL) as httpOnly cookie.
- `accessToken` is stored in memory via Pinia store (`stores/user.js`), never persisted.
- Axios request interceptor attaches `Authorization: Bearer <token>`.
- On 401, a response interceptor silently calls `/api/user/account/refresh_token/`, queues concurrent requests, and retries them with the new token. If refresh fails, user is logged out.

### Backend view pattern

Each API endpoint is a single file under `backend/web/views/`, each exporting a DRF `APIView` subclass. **No DRF serializers are used** — views read `request.data` / `request.FILES` directly and return plain dicts via `Response(data, status=...)`.

**HTTP status code conventions** — never use the default 200 for error responses:
- `200` — success (only for successful operations)
- `400` — client validation error (empty fields, missing required data)
- `401` — authentication failure (wrong password, expired token)
- `404` — resource not found
- `409` — conflict (duplicate username, etc.)
- `500` — server error (unhandled exception)

**Exception handling:** Never use bare `except:`. Always `except Exception as e:` with `logger.exception(...)` before the error response. Every view imports `logging` and has `logger = logging.getLogger(__name__)`.

Models live in `backend/web/models/` — four files: `user.py` (UserProfile), `character.py` (Character, Voice), `friend.py` (Friend, Message, SystemPrompt), `document.py` (UserDocument, DocumentChunk with pgvector VectorField).

### Logging

LOGGING is configured in `backend/backend/settings.py` with console (StreamHandler) + rotating file handler (`logs/web.log`, 10 MB × 5 backups). Both the root logger and the `web` logger are set to INFO level.

All view modules use `logger = logging.getLogger(__name__)`. Use `logger.exception()` on caught errors (equivalent to `logger.error(... exc_info=True)`, captures full traceback).

### Character fields

`Character.profile` has been split into two independent fields:

- **`introduction`** (`max_length=500`) — public intro shown on cards and the `CharacterDetail` modal. Frontend display uses this directly.
- **`system_prompt`** (`max_length=10000`) — full character personality prompt sent to the LLM via `chat/graph.py` and `chat/chat.py`.

The two fields are completely independent — `system_prompt` does NOT include `introduction`. Only `system_prompt` enters the LLM context.

### Character detail → chat flow

On the homepage, clicking a character card opens `CharacterDetail.vue` (a modal) rather than jumping straight to chat. The component:
1. Calls `GET /api/friend/is_friend/?character_id=X` to check friendship status
2. Shows "添加好友" or "开始聊天" button accordingly
3. On button click, calls `POST /api/friend/get_or_create/` then opens `ChatField`

`Character.vue` accepts a `showDetail` prop — when true, the card click opens the detail modal first; when false (friend list page, user space), the old direct-to-chat behavior is preserved.

### LangGraph agent architecture

Two separate LangGraph state graphs:

1. **Chat agent** (`web/views/friend/message/chat/graph.py`) — `deepseek-v4-flash` model with tools: `get_time` and `search_knowledge_base` (pgvector 余弦向量检索，按 `owner_id` 过滤召回全局知识库 + 用户个人文档)。Streams tokens via SSE. Also streams TTS audio chunks (base64 mp3) over the same SSE connection using a separate DashScope WebSocket.

2. **Memory agent** (`web/views/friend/message/memory/graph.py`) — `deepseek-v4-flash` model. 通过 Celery 异步任务 (`web/views/friend/message/memory/tasks.py`) 每 10 条消息触发一次，摘要写入 `Friend.memory` 字段。`last_summarized_count` 字段防止失败重试时遗漏消息。

### Celery async tasks

`web/tasks.py` 是 Celery `autodiscover_tasks()` 的入口文件，所有异步任务通过此文件注册导入：

```python
from web.views.friend.message.memory.tasks import update_memory_task    # Memory Agent
from web.views.document.tasks import process_document_task              # 文档处理
```

`autodiscover_tasks()` 只扫描 `<app>.tasks` 模块，深度嵌套的 task 文件必须在此入口文件中显式导入。

### Frontend knowledge base page

`/knowledge` 路由 → `KnowledgeBase.vue`（`meta: { needLogin: true }`）：
- **UploadZone** — 拖拽/点击上传 .txt/.md/.pdf（≤10MB，前端校验格式+大小）
- **DocumentCard** — 文档卡片，状态标签（pending/processing/completed/failed）
- **useDocumentPolling** — 每 3 秒轮询文档列表，全部到达终态时自动停止，兜底 120 次（6 分钟）超时

### Frontend error handling

**200 = success.** Components no longer check `data.message === 'success'` — HTTP 200 guarantees the operation succeeded.

**4xx/5xx errors go through `catch` blocks.** Components read `e.response?.data?.message` with a fallback string:

```javascript
} catch (e) {
  errorMessage.value = e.response?.data?.message || '网络异常'
}
```

**axios 401 whitelist:** Login/register endpoints are excluded from the 401→token-refresh interceptor (`frontend/src/js/http/api.js`), since a 401 on those means "wrong credentials," not "expired token."

### SSE streaming (chat)

The frontend uses `@microsoft/fetch-event-source` (`js/http/streamApi.js`) to POST to `/api/friend/message/chat/`. The response is `text/event-stream` with JSON lines containing `data.content` (text delta) and `data.audio` (base64 mp3 chunk). Audio is played through browser Media Source Extensions.

### Voice pipeline

- **Input:** `Microphone.vue` uses `@ricky0123/vad-web` (Silero VAD via ONNX/WASM) to detect speech end, captures PCM16 audio, sends it to `/api/friend/message/asr/asr/` → DashScope WebSocket for transcription.
- **Output:** Chat SSE stream carries interleaved text + audio chunks; `InputField.vue` feeds audio into `MediaSource` for real-time playback.

### RAG / knowledge base

`backend/web/documents/` 重构成了三层架构：

```
documents/
├── loaders/          # 文档加载层（抽象接口 + txt/md/pdf 三种 loader）
├── services/         # 服务层（embeddings + chunker 统一切分）
└── utils/            # 兼容旧 import + 系统知识库批量导入
```

- **向量化：** `CustomEmbeddings` 封装 DashScope `text-embedding-v4` API（1024 维）
- **切分：** `RecursiveCharacterTextSplitter(chunk_size=500, overlap=50)`
- **存储：** `DocumentChunk` 模型（pgvector VectorField，HNSW 索引）
- **用户隔离：** `DocumentChunk.owner` 字段，`search_knowledge_base` 按 `WHERE owner_id IS NULL OR owner_id = %s` 同时召回全局 + 个人文档

**API 端点：**

| 端点 | 功能 |
|------|------|
| `POST /api/document/upload/` | 上传文档 → 同步校验 → Celery 异步处理 |
| `GET /api/document/list/` | 用户文档列表 |
| `POST /api/document/remove/` | 删除文档 + 级联 chunks |

**Celery 任务：** `process_document_task(doc_id)` — 文本提取 → 分块 → embedding → 批量写入 DocumentChunk。注册在 `web/tasks.py`。

### Character.photo_url / background_image_url

Use `character.photo_url` and `character.background_image_url` properties instead of `.photo.url` / `.background_image.url`. These safe properties return `''` when no file is associated, preventing `ValueError` crashes.

### Voice.is_builtin

System built-in voices (longanyang/longanhuan) have `is_builtin=True`. The cleanup command skips them. Never delete a voice with `is_builtin=True`.
