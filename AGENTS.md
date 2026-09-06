# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

AI Friends — a full-stack web app where users create AI characters ("friends") and chat with them. Supports text + voice input/output, long-term memory summarization, and RAG-based knowledge retrieval.

- **Backend:** Django 6.0 + Django REST Framework + JWT auth (PostgreSQL 17 + pgvector 0.8)
- **Frontend:** Vue 3 (Composition API) + Vite 7 + Pinia + Vue Router 5 + Tailwind CSS 4 + daisyUI 5
- **AI:** Alibaba DashScope via OpenAI-compatible API (Chat/Memory: deepseek-v4-flash, TTS: cosyvoice-v3-flash, ASR: gummy-realtime-v1, Embedding: text-embedding-v4). LangChain/LangGraph for orchestration. pgvector for vector storage.
- **Voice:** DashScope TTS (WebSocket streaming) + ASR (WebSocket). Browser-side VAD via `@ricky0123/vad-web` (Silero VAD on ONNX).
- **Infrastructure:** Redis 7 (rate limiting + Celery broker), Celery (async tasks), Docker Compose (PG + Redis)

## Commands

### Backend (Python/Django)

```bash
cd backend
pip install -r ../requirements.txt
python manage.py runserver              # Dev server on :8000
python -m pytest web/tests/ -v         # 209 tests
python manage.py clean_dirty_characters --all  # Clean test residue
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

```bash
wsl docker compose up -d   # PostgreSQL 17 + pgvector + Redis 7
cd backend
celery -A backend worker --loglevel=info --pool=solo  # Celery Worker
```

### Production Deployment

Deployment uses the registry flow (local image build → push to Alibaba Cloud ACR → server pull), see `服务器部署.md`:

1. Local: `ACR_IMAGE=<image> ./deploy/build.sh` (multi-stage build: frontend baked into image + collectstatic → push to ACR)
2. Server: `docker compose pull && docker compose up -d` (5 containers, no build, no scp)

## Architecture

### How the stacks connect

The frontend is built into `backend/static/frontend/`. Django serves the SPA via a catch-all route: `web/views/index.py` reads the built `frontend/index.html` (from `STATIC_ROOT` in prod, `static/` in dev), which loads the Vite-built assets. All API routes live under `/api/` in `backend/web/urls.py`.

### Environment / platform modes

`frontend/src/js/config/config.js` auto-detects the platform from Vite MODE and `VITE_PLATFORM` env var. **No manual editing required.**

| Mode | HTTP base | Trigger |
|------|-----------|---------|
| `django` | `http://127.0.0.1:8000` | `npm run dev` (default) |
| `vue` | `http://127.0.0.1:8000` | `VITE_PLATFORM=vue npm run dev` |
| `cloud` | `VITE_CLOUD_BASE` or `https://115.190.245.146` | `npm run build` (default) |
| `docker` | `''` (same-origin) | `VITE_PLATFORM=docker npm run build` |

> Production uses `docker` mode (same-origin): the multi-stage Dockerfile pins `VITE_PLATFORM=docker`, and the frontend ships inside the image. `cloud` mode is deprecated.

### SECRET_KEY enforcement

`DJANGO_SECRET_KEY` is read from environment variable:
- **DEBUG=True**: falls back to `'django-insecure-dev-only-not-for-production'` if not set
- **DEBUG=False**: raises `ImproperlyConfigured` if not set, refusing to start

### JWT auth flow

- Login/register returns `access_token` (2h TTL) in response body + `refresh_token` (7d TTL) as httpOnly cookie.
- `accessToken` is stored in memory via Pinia store (`stores/user.js`), never persisted.
- Axios request interceptor attaches `Authorization: Bearer <token>`.
- On 401, a response interceptor silently calls `/api/user/account/refresh_token/`, queues concurrent requests, and retries them with the new token. If refresh fails, user is logged out.
- Login/register endpoints are whitelisted from the 401→token-refresh interceptor.

### Backend view pattern

Each API endpoint is a single file under `backend/web/views/`, each exporting a DRF `APIView` subclass. **No DRF serializers are used** — views read `request.data` / `request.FILES` directly and return plain dicts via `Response(data, status=...)`.

**HTTP status code conventions:**
- `200` — success only
- `400` — client validation error
- `401` — authentication failure
- `404` — resource not found
- `409` — conflict
- `429` — rate limit exceeded
- `500` — server error
- `503` — service degraded (health check)

**Exception handling:** Never use bare `except:`. Always `except Exception as e:` with `logger.exception(...)`.

### Data models

Models live in `backend/web/models/` — six files:

| File | Models |
|------|--------|
| `user.py` | UserProfile |
| `character.py` | Character, Voice |
| `friend.py` | Friend, Message, SystemPrompt |
| `document.py` | UserDocument, DocumentChunk (pgvector VectorField) |
| `retrieval_trace.py` | RetrievalTrace (RAG retrieval trace) |
| `usage.py` | APIUsage (LLM/TTS/ASR/Embedding usage tracking) |

### Character fields

`Character.profile` has been **split into two independent fields**:

- **`introduction`** (`max_length=500`) — public intro shown on cards and the `CharacterDetail` modal. Frontend display uses this directly.
- **`system_prompt`** (`max_length=10000`) — full character personality prompt sent to the LLM.

The two fields are completely independent — `system_prompt` does NOT include `introduction`. Only `system_prompt` enters the LLM context. Do NOT use the old `character.profile.split('\n')[0]` pattern.

### Character.photo_url / background_image_url

Use `character.photo_url` and `character.background_image_url` properties instead of `.photo.url` / `.background_image.url`. These safe properties return `''` when no file is associated, preventing `ValueError` crashes.

### Character detail → chat flow

On the homepage, clicking a character card opens `CharacterDetail.vue` (a modal) rather than jumping straight to chat. The component:
1. Calls `GET /api/friend/is_friend/?character_id=X` to check friendship status
2. Shows "添加好友" or "开始聊天" button accordingly
3. On button click, calls `POST /api/friend/get_or_create/` then opens `ChatField`

`Character.vue` accepts a `showDetail` prop — when true, the card click opens the detail modal first; when false (friend list page, user space), the old direct-to-chat behavior is preserved.

### LangGraph agent architecture

Two separate LangGraph state graphs:

1. **Chat agent** (`web/views/friend/message/chat/graph.py`) — `deepseek-v4-flash` model with tools: `get_time` and `search_knowledge_base` (pgvector cosine search, JOINs UserDocument for titles, filters by `owner_id IS NULL OR owner_id = %s`). Streams tokens via SSE. Also streams TTS audio chunks (base64 mp3) over the same SSE connection.

2. **Memory agent** (`web/views/friend/message/memory/graph.py`) — `deepseek-v4-flash` model. Triggered via Celery async task every 10 messages, writes summary to `Friend.memory`. `last_summarized_count` prevents message loss on retry failure.

### SystemPrompt 3-layer architecture

`add_system_prompt()` in `chat.py` builds 3 independent SystemMessage layers:

| Layer | Source | Content |
|-------|--------|---------|
| 1 (highest priority) | Code constant `TOOL_RULES` | Tool calling rules (when to use `search_knowledge_base`) |
| 2 | `Character.system_prompt` + `Friend.memory` | Character personality + long-term memory |
| 3 (framework) | DB `SystemPrompt` (title=REPLY) | System-level framework constraints |

Three layers are independent — tool rules cannot be overridden by character personality.

### Celery async tasks

`web/tasks.py` is the autodiscover entry point. Deeply nested task files must be explicitly imported here:

```python
from web.views.friend.message.memory.tasks import update_memory_task
from web.views.document.tasks import process_document_task
```

**Configuration:**
- `CELERY_TASK_ACKS_LATE = True` — tasks return to queue on worker crash
- `CELERY_WORKER_PREFETCH_MULTIPLIER = 1` — one task at a time
- `CELERY_TASK_SOFT_TIME_LIMIT = 120s`, `CELERY_TASK_TIME_LIMIT = 180s`

**Retry strategy (both tasks):**
- 4xx errors (except 429) → permanent failure, no retry, clear `celery_task_id`
- 5xx / 429 / network errors → retry with countdown=10, keep `celery_task_id` for revocation

### Rate limiting

`RateLimitMiddleware` (`web/middleware/rate_limit.py`):
- Redis Lua atomic script (sliding window log algorithm)
- Per-user limiting for authenticated users, per-IP for anonymous
- Only write methods (POST/PUT/PATCH/DELETE) are limited
- Fail-open: requests pass through if Redis is unreachable
- 6 rules: login(5/60s), register(3/60s), chat(20/60s), asr(10/60s), upload(10/60s), default(60/60s)
- Returns HTTP 429 with `Retry-After` header

### API usage tracking

`APIUsage` model tracks all AI calls:
- `llm` — recorded in `chat.py`, `memory/tasks.py` (token_count, duration_ms, success)
- `tts` — recorded in `chat.py` (written from sync context to avoid `SynchronousOnlyOperation`)
- `asr` — recorded in `asr/asr.py`
- `embedding` — recorded in `embeddings.py`

`record_api_usage()` is fire-and-forget — exceptions are caught and logged, never blocking.

### Health check

`GET /api/health/` — three independent component checks:
- DB: `connections['default'].cursor()`
- Redis: `redis.from_url(...).ping()`
- Celery: `app.control.inspect().ping()`
- All pass → HTTP 200; any fail → HTTP 503 with degraded status

### RAG / knowledge base

`backend/web/documents/` — three-layer architecture:

```
documents/
├── loaders/          # Document loaders (abstract interface + txt/md/pdf)
├── services/         # embeddings (DashScope text-embedding-v4, 1024d) + chunker
└── utils/            # System knowledge base import (incremental update)
```

**System knowledge base incremental update** (`insert_documents.py`):
- Uses `DocumentChunk.content_hash` (SHA-256) to compare old vs new chunks
- Skips unchanged chunks — no redundant embedding API calls
- Removes chunks whose index no longer exists in the new version

**API endpoints:**

| Endpoint | Function |
|----------|----------|
| `POST /api/document/upload/` | Upload → magic byte validation → Celery async processing |
| `GET /api/document/list/` | User document list |
| `POST /api/document/remove/` | Delete document → revoke Celery task → cascade delete chunks |

**Document processing reliability:**
- `UserDocument.celery_task_id` tracks async task for revocation
- Upload enqueue failure → `status='failed'` (not stuck in pending)
- Delete checks `celery_task_id` → `app.control.revoke()` (best-effort)
- Task completion/permanent failure clears `celery_task_id`

### RAG citations & RetrievalTrace

- `search_knowledge_base` returns results marked as `[来源N: 文档标题 第M段]`
- System knowledge base (no document) displays as "系统知识库"
- `RetrievalTrace` model records each retrieval: user, query, document, chunk_index, distance
- Chat SSE stream emits `{"citations": [...]}` event before content chunks
- Citation detection uses regex: `\[来源(\d+): (.+?) 第(\d+)段\]`

### Logging & observability

- `RequestIdMiddleware` generates unique UUID per request, sets `X-Request-ID` response header
- Logs `METHOD /path -> STATUS, duration=X.Xms` for every request
- `RequestIdFilter` injects `request_id` into all log records
- Log format: `[{levelname}] {asctime} [{request_id}] {module}: {message}`
- Rotating file handler: `logs/web.log` (10MB × 5 backups)

### SSE streaming (chat)

The frontend uses `@microsoft/fetch-event-source` (`js/http/streamApi.js`) to POST to `/api/friend/message/chat/`. SSE events:
- `data.content` — text delta
- `data.audio` — base64 mp3 chunk (Media Source Extensions)
- `data.citations` — RAG source references (arrives before content)
- `data.error` — error message

### Voice pipeline

- **Input:** `Microphone.vue` uses `@ricky0123/vad-web` (Silero VAD via ONNX/WASM) to detect speech end, captures PCM16 audio, sends to `/api/friend/message/asr/asr/` → DashScope WebSocket for transcription.
- **Output:** Chat SSE stream carries interleaved text + audio chunks; `InputField.vue` feeds audio into `MediaSource` for real-time playback.

### Frontend

#### Toast notification system

- `useToast.js` composable — module-level `reactive()` singleton, `readonly()` exposed
- `ToastContainer.vue` — daisyUI alert styles (success/error/warning/info), `<transition-group>` animations
- Auto-remove (non-error, 3s) + manual close (error stays), max 5 toasts
- Mounted in `App.vue`, first consumer is `KnowledgeBase.vue`
- Static class object for alert colors to avoid Tailwind JIT missing classes

#### Shared composables

- **`useImageCropper.js`** — Wraps Croppie init/crop/destroy. Used by 3 components (character Photo, user Photo, BackgroundImage). Eliminated ~90% duplicate code.
- **`useDocumentPolling.js`** — Polls document list every 3s, auto-stops when all terminal, 120x max (6 min), cleanup on unmount.

#### Knowledge base page

`/knowledge` route → `KnowledgeBase.vue`:
- `UploadZone` — drag/click upload .txt/.md/.pdf (≤10MB, client-side validation)
- `DocumentCard` — status badges (pending/processing/completed/failed)
- `useDocumentPolling` + `useToast` integration

### Django Admin

`web/admin.py` registers all major models:
- `UserDocumentAdmin` — `list_display` with title/owner/file_type/status/chunks_count; `readonly_fields` includes `celery_task_id`/`error_message`; search and filter support
- `DocumentChunkAdmin` — `exclude=('embedding',)` to avoid vector field issues
- `CharacterAdmin`, `FriendAdmin`, `MessageAdmin` — `raw_id_fields` to prevent N+1 queries

### Testing

- 209 tests in `web/tests/`, run with `python -m pytest web/tests/ -v`
- `pytest.ini` defaults to `-m "not slow"` (skips 3 `test_tool_calling.py` tests needing real API_KEY)
- GitHub Actions CI (`.github/workflows/test.yml`) runs on push/PR to master with pgvector service container
- Key fixtures: `_disable_rate_limit_for_tests` (autouse), `media_root` (session, autouse), `pgvector_extension` (session, autouse), `mock_asr_ws`
- Dual-DB: tests use PostgreSQL `aifriends_test` (same engine as dev)
