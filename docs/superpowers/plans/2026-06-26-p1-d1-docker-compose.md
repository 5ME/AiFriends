# P1-D1: Docker Compose 全栈一键部署 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `docker compose up -d` 一键启动全栈 5 容器（PG+Redis+Django+gunicorn+Celery+Nginx），覆盖云服务器生产部署。

**Architecture:** 8 个文件变更（3 新建、5 修改）。Django + Celery 用同一 `python:3.12-slim` 镜像、不同 CMD。Nginx 反代 TCP `django:8000`。前端在宿主机 `npm run build` → `collectstatic` → volume mount 进 Nginx。

**Tech Stack:** Docker Compose v3.8+, python:3.12-slim, nginx:1.27-alpine, pgvector/pgvector:pg17, redis:7-alpine

---

### Task 1: backend/Dockerfile + backend/.dockerignore

**Files:**
- Create: `.dockerignore` (project root)
- Create: `backend/Dockerfile`

- [ ] **Step 1: Create .dockerignore (project root)**

```dockerignore
# 版本控制 / 文档 / 工具（加速 build context 传输）
.git/
docs/
.codegraph/
frontend/

# 后端 — 环境/安全（绝不能进镜像）
backend/.env

# 后端 — 运行时数据 / 缓存（runtime volume mount 或宿主机生成）
backend/db.sqlite3
backend/logs/
backend/media/
backend/static/
backend/staticfiles/
backend/rag_eval_output/
backend/.pytest_cache/

# Python 编译缓存（任意层级）
**/__pycache__/
**/*.pyc
**/*.pyo
```

- [ ] **Step 2: Create backend/Dockerfile**

```dockerfile
# backend/Dockerfile
FROM python:3.12-slim

# 不缓冲 stdout/stderr（容器日志实时可见）+ 不写 .pyc
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 构建工具（源码安装的依赖兜底）+ curl（Django healthcheck 探测 /api/health/）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Build context 是项目根，COPY 相对 context
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

EXPOSE 8000
CMD ["gunicorn", "--workers", "3", "--graceful-timeout", "30", "--bind", "0.0.0.0:8000", "backend.wsgi:application"]
```

- [ ] **Step 3: Verify Dockerfile syntax**

Run: `docker build --dry-run -f backend/Dockerfile . 2>&1 | head -5`
Expected: No syntax errors (will fail on actual build without docker, but `docker build --check` validates syntax if available; otherwise skip)

- [ ] **Step 4: Commit**

```bash
git add .dockerignore backend/Dockerfile
git commit -m "feat(d1): add Dockerfile + .dockerignore for Django/Celery

- python:3.12-slim base, gcc+libpq-dev+curl
- Django + Celery share same image, different command
- No collectstatic in build (needs SECRET_KEY from .env at runtime)
- No USER app (volume mount UID mismatch on host)"
```

---

### Task 2: init.sql 精简

**Files:**
- Modify: `init.sql`

- [ ] **Step 1: Replace init.sql content**

Current content (6 lines — CREATE USER, CREATE DATABASE, GRANT, \c, GRANT schema, CREATE EXTENSION):

Replace with:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

**Rationale:** PostgreSQL Docker 镜像的 `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` 环境变量自动处理用户和数据库创建。`init.sql` 只需装 pgvector 扩展。

- [ ] **Step 2: Verify the SQL is syntactically correct**

Run: `cat init.sql`
Expected: Single line `CREATE EXTENSION IF NOT EXISTS vector;`

- [ ] **Step 3: Commit**

```bash
git add init.sql
git commit -m "refactor(d1): simplify init.sql — only pgvector extension

PG user/DB creation delegated to POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB
Docker env vars. init.sql now only runs CREATE EXTENSION IF NOT EXISTS vector."
```

---

### Task 3: nginx.conf

**Files:**
- Create: `nginx.conf` (project root)

- [ ] **Step 1: Create nginx.conf**

```nginx
# nginx.conf — AI Friends Docker Compose 反向代理
server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name _;

    ssl_certificate /etc/nginx/ssl/aifriends-selfsigned.crt;
    ssl_certificate_key /etc/nginx/ssl/aifriends-selfsigned.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    access_log /var/log/nginx/aifriends-access.log;
    error_log  /var/log/nginx/aifriends-error.log;

    # 文档/图片上传 10MB（nginx 默认 1MB 会拦截知识库上传和 ASR 音频 → 413）
    client_max_body_size 10m;

    location /static/ {
        alias /app/staticfiles/;
        expires 30d;
    }

    location /static/frontend/vad/ {
        alias /app/staticfiles/frontend/vad/;
        expires off;
        add_header Cache-Control "public, max-age=2592000, immutable";
    }

    location /media/ {
        alias /app/media/;
        expires 30d;
    }

    location / {
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_pass http://django:8000;

        # SSE 聊天流 + ASR：关闭缓冲 + HTTP/1.1 + 延长读超时，
        # 保证实时 token/音频推送不被 nginx 缓冲或 60s 超时截断
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add nginx.conf
git commit -m "feat(d1): add nginx.conf for Docker Compose reverse proxy

- HTTP 80 → 301 HTTPS 443
- /static/* → /app/staticfiles/ (collectstatic 产物)
- /media/*  → /app/media/ (用户上传)
- /*         → proxy_pass django:8000 (TCP, not unix socket)"
```

---

### Task 4: Django settings.py — SECURE_PROXY_SSL_HEADER

**Files:**
- Modify: `backend/backend/settings.py`

- [ ] **Step 1: Add SECURE_PROXY_SSL_HEADER**

Insert after `SECRET_KEY` block (after line 39 or near other security settings), before `ALLOWED_HOSTS` or after `ALLOWED_HOSTS`:

```python
# 生产环境信任 Nginx 反代的 HTTPS（Docker 下 X-Forwarded-Proto 由 Nginx 设置）
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
```

- [ ] **Step 2: Verify Django configuration**

Run:
```powershell
cd backend
$env:DJANGO_DEBUG = "false"
$env:DJANGO_SECRET_KEY = "test-key-for-check-only"
python manage.py check
```

Expected:
```
System check identified no issues (0 silenced).
```

- [ ] **Step 3: Commit**

```bash
git add backend/backend/settings.py
git commit -m "feat(d1): add SECURE_PROXY_SSL_HEADER for Nginx HTTPS reverse proxy

Only active when DEBUG=False. Trusts X-Forwarded-Proto header set by Nginx
so Django generates https:// URLs behind the reverse proxy."
```

---

### Task 5: .env.example — Docker 环境变量差异标注

**Files:**
- Modify: `backend/.env.example`

- [ ] **Step 1: Update .env.example with Docker comments**

Current content needs 3 host values annotated with Docker alternatives:

```bash
API_KEY=
API_BASE=
WSS_URL=
VOICE_URL=

# PostgreSQL 数据库
# 本地开发: PG_HOST=127.0.0.1
# Docker:    PG_HOST=postgres
PG_HOST=
PG_PORT=5432
PG_NAME=
PG_USER=
PG_PASSWORD=

# 以下 OSS 配置暂时还没有用到
OSS_ACCESS_KEY_ID=
OSS_ACCESS_KEY_SECRET=
OSS_BUCKET=
OSS_REGION=
OSS_ENDPOINT=

# Django 核心配置
# 本地开发: DJANGO_DEBUG=True
# Docker:    DJANGO_DEBUG=False
DJANGO_SECRET_KEY=
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

# Celery broker（异步任务队列）
# 本地开发: CELERY_BROKER_URL=redis://127.0.0.1:6379/0
# Docker:    CELERY_BROKER_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/0

# 生产部署配置
DJANGO_MEDIA_URL=http://your-server/media/
DJANGO_CORS_ORIGINS=http://localhost:5173,https://your-server

# Redis URL for rate limiting (DB /1, separate from Celery broker /0)
# 本地开发: REDIS_URL=redis://127.0.0.1:6379/1
# Docker:    REDIS_URL=redis://redis:6379/1
REDIS_URL=redis://127.0.0.1:6379/1
```

- [ ] **Step 2: Verify no syntax issues**

Run: `cat backend/.env.example`
Expected: File contains Docker annotations for PG_HOST, CELERY_BROKER_URL, REDIS_URL, DJANGO_DEBUG

- [ ] **Step 3: Commit**

```bash
git add backend/.env.example
git commit -m "docs(d1): annotate .env.example with Docker Compose host differences

Add comments showing local dev vs Docker values for:
- PG_HOST (127.0.0.1 vs postgres)
- CELERY_BROKER_URL (127.0.0.1 vs redis)
- REDIS_URL (127.0.0.1 vs redis)
- DJANGO_DEBUG (True vs False)"
```

---

### Task 6: docker-compose.yml — 从 2 服务扩展到 5 服务

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Replace docker-compose.yml with full 5-service version**

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg17
    container_name: ai-friends-db
    environment:
      POSTGRES_USER: aifriends
      POSTGRES_PASSWORD: ${PG_PASSWORD}
      POSTGRES_DB: aifriends
    ports:
      - "127.0.0.1:55432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U aifriends"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: ai-friends-redis
    ports:
      - "127.0.0.1:6379:6379"
    volumes:
      - redis-data:/data
    command: redis-server --save 60 1 --loglevel warning
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  django:
    build:
      context: .
      dockerfile: backend/Dockerfile
    container_name: ai-friends-web
    command: gunicorn --workers 3 --graceful-timeout 30 --bind 0.0.0.0:8000 backend.wsgi:application
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./backend/staticfiles:/app/staticfiles
      - ./backend/media:/app/media
      - ./backend/logs:/app/logs
    env_file:
      - .env
    restart: unless-stopped
    healthcheck:
      # 存活探测：仅检查 gunicorn 是否接受连接，不依赖 DB/Celery（避免 Celery 冷启动拖垮启动顺序）
      # 深度 /api/health/（含 Celery）留给外部监控；liveness/readiness 正式拆分见 D2
      test: ["CMD", "python", "-c", "import socket; socket.create_connection(('127.0.0.1', 8000), 3).close()"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 30s

  celery:
    build:
      context: .
      dockerfile: backend/Dockerfile
    container_name: ai-friends-celery
    command: celery -A backend worker -l info -c 1
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./backend/media:/app/media
      - ./backend/logs:/app/logs
    env_file:
      - .env
    restart: unless-stopped

  nginx:
    image: nginx:1.27-alpine
    container_name: ai-friends-nginx
    ports:
      - "443:443"
      - "80:80"
    depends_on:
      django:
        condition: service_healthy
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./backend/staticfiles:/app/staticfiles:ro
      - ./backend/media:/app/media:ro
      - ./ssl:/etc/nginx/ssl:ro
    restart: unless-stopped

volumes:
  postgres-data:
  redis-data:
```

- [ ] **Step 2: Verify compose file syntax**

Run:
```bash
docker compose config 2>&1
```

Expected: Rendered compose config, no errors. (If `docker compose` not available locally, check with a YAML linter or visual inspection.)

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(d1): upgrade docker-compose.yml from 2 to 5 services

Add django (gunicorn), celery worker, and nginx services.
- All services use healthchecks with proper depends_on chains
- PG/Redis ports bind 127.0.0.1; Nginx binds all interfaces
- Celery shares Django Dockerfile, different command
- Static/media/logs via host volume mounts
- Nginx waits for django service_healthy"
```

---

### Task 7: 服务器部署.md — 更新为 Docker Compose 流程

**Files:**
- Modify: `服务器部署.md`

- [ ] **Step 1: Rewrite 服务器部署.md**

Replace entire content with Docker Compose based deployment guide:

```markdown
## 服务器部署（Docker Compose）

`docker compose up -d` 一键启动全栈：PostgreSQL 17 + Redis 7 + Django/gunicorn + Celery Worker + Nginx。

### 宿主机前置依赖

| 依赖 | 用途 |
|------|------|
| Docker + Docker Compose v2 | 运行全栈容器 |
| Node.js + npm | 前端构建（`npm run build`） |
| Python 3.12 + 项目依赖 | 静态文件收集（`collectstatic`，不联网/不连库） |

> 前端构建和 collectstatic 在宿主机执行（产物通过 volume 挂载进容器）；数据库迁移在容器内执行（宿主机无法解析 compose 服务名 `postgres`）。

#### 安装 Docker（首次）

```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker $USER  # 重新登录生效
```

### 首次部署

```bash
cd ~/ai-friends

# 1. 环境变量（项目根目录 .env，注意不是 backend/.env）
cp .env.example .env
# 编辑 .env，至少填入：
#   - API_KEY / API_BASE / WSS_URL / VOICE_URL（DashScope 密钥）
#   - DJANGO_SECRET_KEY（随机长字符串）
#   - PG_PASSWORD（数据库密码，同时用作 POSTGRES_PASSWORD，不能为空）
#   - DJANGO_ALLOWED_HOSTS / DJANGO_CORS_ORIGINS / DJANGO_MEDIA_URL（服务器 IP）
# 已预填的 Docker 专用值无需改：PG_HOST=postgres、CELERY_BROKER_URL/REDIS_URL 用 redis 服务名、DJANGO_DEBUG=False

# 2. SSL 自签证书（必须在 up 之前，否则 nginx 找不到证书会崩溃重启）
mkdir -p ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/aifriends-selfsigned.key \
  -out ssl/aifriends-selfsigned.crt

# 3. 前端构建（产物 → backend/static/frontend/）
cd frontend && npm install && npm run build && cd ..

# 4. 收集静态文件（→ backend/staticfiles/，Nginx 直接 serve）
cd backend && python manage.py collectstatic --noinput && cd ..

# 5. 数据库迁移（容器内执行，自动拉起 postgres+redis 后运行 migrate 再退出）
docker compose run --rm django python manage.py migrate

# 6.（可选）创建管理员账号
docker compose run --rm django python manage.py createsuperuser

# 7. 启动全栈
docker compose up -d

# 8. 查看状态（全部应为 running / healthy）
docker compose ps
```

### 更新部署

```bash
cd ~/ai-friends
git pull

# 前端 + 静态文件重建
cd frontend && npm run build && cd ..
cd backend && python manage.py collectstatic --noinput && cd ..

# 应用新迁移
docker compose run --rm django python manage.py migrate

# 重建镜像并重启
docker compose up -d --build
```

### 常用运维命令

```bash
docker compose ps                       # 容器状态
docker compose logs -f                  # 所有日志
docker compose logs -f django           # 单个服务日志
docker compose restart django           # 重启单个服务
docker compose down                     # 停止所有容器
docker compose down -v                  # 停止并删除数据卷（⚠️ 数据库数据会丢失）
```

### 容器拓扑

```
Nginx (:443/:80)  →  Django/gunicorn (:8000)  →  PostgreSQL
                                              →  Redis
                  Celery Worker               →  PostgreSQL
                                              →  Redis
```

| 容器 | 镜像 | 对外端口 |
|------|------|---------|
| ai-friends-nginx | nginx:1.27-alpine | 443, 80 |
| ai-friends-web | 本地构建（gunicorn） | — |
| ai-friends-celery | 本地构建（worker） | — |
| ai-friends-db | pgvector/pgvector:pg17 | 127.0.0.1:55432（仅本机） |
| ai-friends-redis | redis:7-alpine | 127.0.0.1:6379（仅本机） |

### 注意事项

- **端口冲突**：若服务器已运行 nginx/apache 占用 80/443，需先停掉或修改 compose 端口映射
- **启动顺序**：postgres/redis healthy → django/celery → nginx，由 compose 的 `depends_on` 自动编排
- **数据持久化**：`postgres-data` / `redis-data` 为 named volume；`media` / `logs` / `staticfiles` 为 bind mount
- **PG/Redis 端口**：仅绑定 `127.0.0.1`（外网由安全组阻断，宿主机可 `psql -h 127.0.0.1 -p 55432` 调试）
- **自签证书**：浏览器会提示不安全，属预期（IP 部署无域名证书）
```

- [ ] **Step 2: Commit**

```bash
git add 服务器部署.md
git commit -m "docs(d1): rewrite deployment guide for Docker Compose

Replace manual gunicorn+systemd flow with docker compose up -d.
Add: Docker install, SSL setup, .env config, ops commands, container topology table."
```

---

### Task 8: 端到端验证

**Files:** (none — verification only)

- [ ] **Step 1: Verify all backend tests still pass**

Run:
```powershell
cd backend
conda activate py312
python -m pytest web/tests/ -v --timeout 60 2>&1 | tail -20
```

Expected: All existing tests pass (no regressions from settings.py change).

- [ ] **Step 2: Verify docker compose config is valid**

Run:
```bash
docker compose config 2>&1 | head -20
```

Expected: Rendered compose config, no errors.

- [ ] **Step 3: Verify docker build succeeds**

Run:
```bash
docker compose build django 2>&1
```

Expected: Image builds successfully. Note: requires Docker daemon running and valid `requirements.txt`.

- [ ] **Step 4: Verify health endpoint logic**

Run:
```powershell
cd backend
$env:DJANGO_SETTINGS_MODULE = "backend.settings"
$env:DJANGO_DEBUG = "false"
$env:DJANGO_SECRET_KEY = "verify-test-key-123"
python -c "import django; django.setup(); from django.conf import settings; print('SECURE_PROXY_SSL_HEADER:', getattr(settings, 'SECURE_PROXY_SSL_HEADER', 'NOT SET'))"
```

Expected:
```
SECURE_PROXY_SSL_HEADER: ('HTTP_X_FORWARDED_PROTO', 'https')
```

- [ ] **Step 5: Final checklist**

Manual verification items (require Docker + cloud server):
- [ ] `docker compose up -d` 所有 5 容器启动
- [ ] `docker compose ps` 全部 healthy
- [ ] `curl -k https://localhost/api/health/` 返回 `{"status": "ok"}`
- [ ] 浏览器访问 `https://<server-ip>/` 正常加载前端 SPA
- [ ] SSE 聊天功能正常（LLM 流式响应 + TTS 音频）

---

## 执行顺序

```
Task 1 (Dockerfile) ─┬─ Task 2 (init.sql) ─┬─ Task 6 (docker-compose.yml) → Task 7 (部署文档) → Task 8 (验证)
                      ├─ Task 3 (nginx.conf) ┤
                      ├─ Task 4 (settings.py) ┤
                      └─ Task 5 (.env.example) ┘
```

Task 1-5 之间无依赖可并行。Task 6 依赖 Task 1（compose 引用 Dockerfile）+ Task 2/3（compose volume mount 引用 `./init.sql` 和 `./nginx.conf`，文件不存在时 Docker 会创建空目录导致运行时错误）。Task 7 最后更新文档。Task 8 收尾验证。

## 风险

| 风险 | 缓解 |
|------|------|
| Docker build 在本地 Windows 上无法测试 | CI 或云服务器上验证；本地至少验证 compose 语法和 Dockerfile 语法 |
| `python:3.12-slim` 缺少某些运行时依赖 | 首次 build 后逐容器检查日志；需要时补 apt 包 |
| Celery beat 与 worker 同容器可能冲突 | 当前 `celery worker` 不含 `-B`，beat 通过 compose 单独 service 或暂不启用 |
| 云服务器上 `npm install` 内存不足 | 本地 build 后 scp 产物，或在服务器上 `npm ci --production` |
