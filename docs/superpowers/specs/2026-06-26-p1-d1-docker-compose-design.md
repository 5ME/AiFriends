# P1-D1: Docker Compose 全栈一键部署 设计文档

> 状态：草稿 | 2026-06-26

## 一、背景

当前生产部署依赖手工操作：`npm run build` → `scp` 传文件 → `gunicorn` → `celery worker &` → `systemd`，流程长且易出错。docker-compose.yml 只有 PG + Redis，Django/Celery/Nginx 未容器化。

**目标：** `docker compose up -d` 一键启动全栈，覆盖云服务器生产部署。

**不做：** 本地开发容器化（本地直接用 `python manage.py runserver` 更快）。

## 二、容器拓扑

```
5 个容器 + 1 个自定义网络 + 2 个数据卷:

┌─ Nginx (1.27-alpine) ──────────────┐
│  :443 SSL + :80 → 301              │
│  /static/* → 直接 serve            │
│  /media/*  → 直接 serve            │
│  /*        → proxy_pass django     │
└──────┬─────────────────────────────┘
       │ TCP :8000
┌─ Django (gunicorn) ────────────────┐
│  python:3.12-slim                  │
│  gunicorn workers: 3               │
│  bind 0.0.0.0:8000                 │
│  依赖: postgres + redis (healthy)  │
└──┬──────────┬──────────────────────┘
   │          │
┌──▼──────┐ ┌─▼───────────┐
│ PG 17   │ │ Redis 7     │
│ :5432   │ │ :6379       │
│ volume  │ │ volume      │
│ health  │ │ health      │
└─────────┘ └─────────────┘

┌─ Celery Worker ────────────────────┐
│  与 Django 同镜像，不同 CMD        │
│  celery worker -c 1                │
│  依赖: postgres + redis            │
│  Celery Beat 内置（定时任务）       │
└────────────────────────────────────┘
```

### 端口映射

| 端口 | 绑定 | 说明 |
|------|------|------|
| `443:443` | 所有接口 | Nginx HTTPS（对外服务，不能 bind 127.0.0.1） |
| `80:80` | 所有接口 | Nginx HTTP → 301 HTTPS |
| `127.0.0.1:55432:5432` | 仅本机 | PG（仅本机调试，安全组不开） |
| `127.0.0.1:6379:6379` | 仅本机 | Redis（仅本机调试，安全组不开） |

### 挂载

| 路径 | 说明 |
|------|------|
| `./backend/staticfiles:/app/staticfiles` | collectstatic 产物 → Nginx serve |
| `./backend/media:/app/media` | 用户上传文件（Django + Nginx 都读） |
| `./backend/logs:/app/logs` | Django 日志持久化 |
| `./init.sql:/docker-entrypoint-initdb.d/init.sql` | PG 初始化（建库 + vector 扩展） |
| `./nginx.conf:/etc/nginx/conf.d/default.conf` | Nginx 配置 |
| `./ssl:/etc/nginx/ssl:ro` | SSL 证书（只读） |

## 三、Dockerfile

Django 和 Celery Worker 使用同一镜像、不同 `command`。

```dockerfile
# backend/Dockerfile
FROM python:3.12-slim

# gcc + libpq-dev: psycopg2 编译
# curl: Django healthcheck（gunicorn 容器内用 curl 探测 /api/health/）
RUN apt-get update && apt-get install -y \
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

**要点：**
- Build context = 项目根（需要 `requirements.txt`）
- **不做 `collectstatic`**：Docker build 时没有 `.env` → `SECRET_KEY` 未设 → `DEBUG=False` 下 `ImproperlyConfigured` 崩溃。collectstatic 在宿主机部署流程中执行，运行时通过 volume mount 挂入 Nginx。
- **不切 `USER app`**：容器内非 root 用户的 UID 与宿主不一致时，volume mount 的 `media/` / `logs/` 会 Permission denied。单机部署容器内 root 可接受。
- 不安装 Node（前端在宿主机 build）
- 不依赖 conda，直接用 pip
- `graceful-timeout 30`（默认值）：SSE 聊天流可能持续几十秒，3s 过于激进

### .dockerignore

```
# 环境/安全
.env
.git/

# Python 编译缓存
__pycache__/
*.pyc
*.pyo
.pytest_cache/

# 数据/运行时（volume mount 或在宿主机）
logs/
media/
staticfiles/

# 前端（不进入镜像，宿主机 build）
frontend/

# 文档/工具
docs/
.codegraph/
```

## 四、docker-compose.yml

完整 5 服务编排，在现有文件上扩展。

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

## 五、Nginx 配置

基于现有 `服务器部署.md` 中 Nginx 配置，适配 Docker：

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

**与裸机配置的唯一差异：**
- `proxy_pass http://unix:...sock` → `proxy_pass http://django:8000`
- 文件路径从 `/home/gqyin/ai-friends/backend/` → `/app/`

## 六、Django settings 适配

`backend/backend/settings.py` 加 2 行：

```python
# 生产环境信任 Nginx 反代的 HTTPS
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
```

不改的部分（已从 env 读取，天然适配 Docker）：
- `DATABASES` — `PG_HOST=postgres` 即可
- `CELERY_BROKER_URL` — `CELERY_BROKER_URL=redis://redis:6379/0` 即可
- `REDIS_URL` — `REDIS_URL=redis://redis:6379/1` 即可
- `CORS_ALLOWED_ORIGINS` — 从 `DJANGO_CORS_ORIGINS` 读取
- `MEDIA_URL` — 从 `DJANGO_MEDIA_URL` 读取

## 七、init.sql 精简

PG 用户/库创建交给 Docker 原生 env 变量（`POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`），`init.sql` 只保留 pgvector 扩展：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

## 八、.env 环境变量

以现有 `.env.example` 为基准，Docker 环境需调整的值（其余不变）：

```bash
# 数据库 — host 从 127.0.0.1 改为 compose 服务名
PG_HOST=postgres
PG_PORT=5432
PG_NAME=aifriends
PG_USER=aifriends
PG_PASSWORD=<与 docker-compose 中 POSTGRES_PASSWORD 一致>

# Django — 生产模式
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=<服务器 IP>

# Celery / Redis — host 从 127.0.0.1 改为 compose 服务名
CELERY_BROKER_URL=redis://redis:6379/0
REDIS_URL=redis://redis:6379/1

# CORS / Media
DJANGO_CORS_ORIGINS=https://<服务器 IP>
DJANGO_MEDIA_URL=https://<服务器 IP>/media/
```

> **Docker 部署用的是项目根 `.env`**（从新增的根 `.env.example` 拷贝），与本地开发的 `backend/.env` 是两份独立文件。compose 的 `${PG_PASSWORD}` 插值和各服务的 `env_file` 都只读项目根 `.env`；根 `.env` 用 compose 服务名（`postgres`/`redis`）作 host，而 `backend/.env` 用 `127.0.0.1`，在容器内不可达。

## 九、部署流程

### 首次部署

```bash
# 1. 克隆代码
git clone ... && cd ai-friends

# 2. 前端构建
cd frontend && npm install && npm run build

# 3. 静态文件收集
cd ../backend
cp .env.example .env   # 按 §八 填入真实值
python manage.py collectstatic --noinput

# 4. SSL 证书准备（已有或新生成）
mkdir -p ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/aifriends-selfsigned.key \
  -out ssl/aifriends-selfsigned.crt

# 5. 启动所有服务
cd ..
docker compose up -d
```

### 更新部署

```bash
git pull
cd frontend && npm run build && cd ..
cd backend && python manage.py collectstatic --noinput && cd ..
docker compose up -d --build   # 重建 Django/Celery 镜像
```

## 十、文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/Dockerfile` | **新建** | Django + Celery 共用镜像 |
| `docker-compose.yml` | **修改** | 从 2 服务扩到 5 服务 |
| `nginx.conf` | **新建** | Nginx 反代配置（项目根目录） |
| `backend/.dockerignore` | **新建** | 排除不用进镜像的文件 |
| `init.sql` | **修改** | 精简为只建 vector 扩展 |
| `backend/backend/settings.py` | **修改** | 加 SECURE_PROXY_SSL_HEADER（2 行） |
| `backend/.env.example` | **修改** | 标注 Docker 环境的 host 差异 |
| `服务器部署.md` | **修改** | 更新为 Docker Compose 流程 |

## 十一、不做的

- ❌ 本地开发 Docker 化（runserver 更快）
- ❌ 前端容器化 / 多阶段 Docker build（复杂度收益不成比例）
- ❌ Dockerfile 内装 Node（构建慢、镜像大）
- ❌ SSL 证书自动签发（保持现有 openssl 自签流程）
- ❌ CI/CD 自动构建 push 镜像（Phase D 不做）

## 十二、变更记录

| # | 时间 | 变更 | 原因 |
|---|------|------|------|
| 1 | 2026-06-26 | 初版 | Brainstorming → 设计确认 |
| 2 | 2026-06-26 | 7 处修复 | Review: 移除 Dockerfile collectstatic、修复端口表 Nginx bind、Celery 依赖改为 PG+Redis、移除 USER app、扩展 .dockerignore、加 Django healthcheck、graceful-timeout 30s |
| 3 | 2026-06-26 | nginx.conf 加 client_max_body_size 10m + SSE proxy 设置（buffering off / http 1.1 / read_timeout 300s） | Task 3 code review: 默认 1MB 拦上传、默认 60s 截断 SSE 流 |
| 4 | 2026-06-26 | django healthcheck 改 socket 存活探测（解耦 Celery）+ 新增根 .env.example | Task 6 code review: /api/health/ 含 Celery 检查会拖垮启动顺序；根 .env 缺失导致 compose 硬失败 |
