# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Friends — a full-stack web app where users create AI characters ("friends") and chat with them. Supports text + voice input/output, long-term memory summarization, and RAG-based knowledge retrieval.

- **Backend:** Django 6.0 + Django REST Framework + JWT auth (SQLite)
- **Frontend:** Vue 3 (Composition API) + Vite 7 + Pinia + Vue Router 5 + Tailwind CSS 4 + daisyUI 5
- **AI:** Alibaba DashScope (Qwen models) via OpenAI-compatible API. LangChain/LangGraph for orchestration. LanceDB for vector storage.
- **Voice:** DashScope TTS (WebSocket streaming) + ASR (WebSocket). Browser-side VAD via `@ricky0123/vad-web` (Silero VAD on ONNX).

## Commands

### Backend (Python/Django)

Uses miniconda environment `py312`. Activate with `conda activate py312` before running commands.

```bash
cd backend
pip install -r requirements.txt
# 本地调试前将 settings.py 中 DEBUG 改为 True
python manage.py runserver              # Dev server on :8000
python -m pytest web/tests/ -v         # Run all backend tests (48 tests)
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

### Production Deployment

1. Set `platform = 'cloud'` in `frontend/src/js/config/config.js`
2. `cd frontend && npm run build`
3. `cd backend && python manage.py collectstatic`
4. Start gunicorn: `gunicorn --workers 3 --bind unix:gunicorn.sock backend.wsgi:application`
5. Nginx reverse-proxies to the gunicorn socket (see `服务器部署.md` for full Nginx config)

## Architecture

### Testing (pytest)

- Tests in `web/tests/`, run with `python -m pytest web/tests/ -v`
- `conftest.py` provides global fixtures: `api_client`, `user`, `auth_client`, `character`, `friend`, etc.
- `media_root` fixture (autouse, session-scoped) redirects test uploads to a temp directory — test files never touch real `media/`
- Tests use `model_bakery` (baker.make) + `pytest-django` transaction rollback

### How the stacks connect

The frontend is built into `backend/static/frontend/`. Django serves the SPA via a catch-all route: `web/views/index.py` renders `templates/index.html`, which loads the Vite-built assets. All API routes live under `/api/` in `backend/web/urls.py`.

### Environment / platform modes

`frontend/src/js/config/config.js` exports a `platform` variable with three modes that control all base URLs:

| Mode | HTTP base | Used for |
|------|-----------|----------|
| `vue` | `http://127.0.0.1:8000` | Frontend-only dev (Vite proxies to Django) |
| `django` | `http://127.0.0.1:8000` | Backend dev (Django serves everything) |
| `cloud` | `https://115.190.245.146` | Production |

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

Models live in `backend/web/models/` — three files: `user.py` (UserProfile), `character.py` (Character, Voice), `friend.py` (Friend, Message, SystemPrompt).

### Logging

LOGGING is configured in `backend/backend/settings.py` with console (StreamHandler) + rotating file handler (`logs/web.log`, 10 MB × 5 backups). Both the root logger and the `web` logger are set to INFO level.

All view modules use `logger = logging.getLogger(__name__)`. Use `logger.exception()` on caught errors (equivalent to `logger.error(... exc_info=True)`, captures full traceback).

### Character.profile convention

The `Character.profile` field has a dual role: it serves as both the user-facing character introduction AND the LLM system prompt. The convention is:

- **First line** (`\n`-delimited) = public introduction shown on cards and the `CharacterDetail` modal
- **Full text** = sent to the LLM as part of the system prompt in `chat/graph.py`

When displaying profile to users, always split on `\n` and show only the first line: `character.profile.split('\n')[0]`.

### Character detail → chat flow

On the homepage, clicking a character card opens `CharacterDetail.vue` (a modal) rather than jumping straight to chat. The component:
1. Calls `GET /api/friend/is_friend/?character_id=X` to check friendship status
2. Shows "添加好友" or "开始聊天" button accordingly
3. On button click, calls `POST /api/friend/get_or_create/` then opens `ChatField`

`Character.vue` accepts a `showDetail` prop — when true, the card click opens the detail modal first; when false (friend list page, user space), the old direct-to-chat behavior is preserved.

### LangGraph agent architecture

Two separate LangGraph state graphs:

1. **Chat agent** (`web/views/friend/message/chat/graph.py`) — `deepseek-v3.2` model with tools: `get_time` and `search_knowledge_base` (LanceDB vector search over Bailian docs). Streams tokens via SSE. Also streams TTS audio chunks (base64 mp3) over the same SSE connection using a separate DashScope WebSocket.

2. **Memory agent** (`web/views/friend/message/memory/graph.py`) — `tongyi-xiaomi-analysis-flash` model. Triggers every 10 messages to summarize conversation and write into `Friend.memory` field.

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

`backend/web/documents/` contains LanceDB vector storage and a custom embeddings wrapper (`custom_embeddings.py`) that calls DashScope's embedding API. Documents are inserted via `insert_documents.py`. The chat agent's `search_knowledge_base` tool queries this store.

### Character.photo_url / background_image_url

Use `character.photo_url` and `character.background_image_url` properties instead of `.photo.url` / `.background_image.url`. These safe properties return `''` when no file is associated, preventing `ValueError` crashes.

### Voice.is_builtin

System built-in voices (longanyang/longanhuan) have `is_builtin=True`. The cleanup command skips them. Never delete a voice with `is_builtin=True`.
