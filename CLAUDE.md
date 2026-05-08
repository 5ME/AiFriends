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

```bash
cd backend
pip install -r requirements.txt
python manage.py runserver              # Dev server on :8000
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

Models live in `backend/web/models/` — three files: `user.py` (UserProfile), `character.py` (Character, Voice), `friend.py` (Friend, Message, SystemPrompt).

### LangGraph agent architecture

Two separate LangGraph state graphs:

1. **Chat agent** (`web/views/friend/message/chat/graph.py`) — `deepseek-v3.2` model with tools: `get_time` and `search_knowledge_base` (LanceDB vector search over Bailian docs). Streams tokens via SSE. Also streams TTS audio chunks (base64 mp3) over the same SSE connection using a separate DashScope WebSocket.

2. **Memory agent** (`web/views/friend/message/memory/graph.py`) — `tongyi-xiaomi-analysis-flash` model. Triggers every 10 messages to summarize conversation and write into `Friend.memory` field.

### SSE streaming (chat)

The frontend uses `@microsoft/fetch-event-source` (`js/http/streamApi.js`) to POST to `/api/friend/message/chat/`. The response is `text/event-stream` with JSON lines containing `data.content` (text delta) and `data.audio` (base64 mp3 chunk). Audio is played through browser Media Source Extensions.

### Voice pipeline

- **Input:** `Microphone.vue` uses `@ricky0123/vad-web` (Silero VAD via ONNX/WASM) to detect speech end, captures PCM16 audio, sends it to `/api/friend/message/asr/asr/` → DashScope WebSocket for transcription.
- **Output:** Chat SSE stream carries interleaved text + audio chunks; `InputField.vue` feeds audio into `MediaSource` for real-time playback.

### RAG / knowledge base

`backend/web/documents/` contains LanceDB vector storage and a custom embeddings wrapper (`custom_embeddings.py`) that calls DashScope's embedding API. Documents are inserted via `insert_documents.py`. The chat agent's `search_knowledge_base` tool queries this store.
