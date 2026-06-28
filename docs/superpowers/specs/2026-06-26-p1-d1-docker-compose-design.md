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

### .dockerignore（项目根）

```
# 版本控制 / 文档 / 工具（加速 build context 传输）
.git/
docs/
.codegraph/
frontend/

# 环境/安全（绝不能进镜像；/.env 是 Docker 部署用的根 .env，不能匹配 .env.example）
/.env
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

## 四、docker-compose.yml

完整 5 服务编排，在现有文件上扩展。

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg17
    container_name: ai-friends-db
    environment:
      POSTGRES_USER: aifriends
      # :? 必填校验 — PG_PASSWORD 空/未设时 compose 在 up 最前面就报错（避免 PG init 失败或 PG/Django 密码不一致）
      POSTGRES_PASSWORD: "${PG_PASSWORD:?PG_PASSWORD 未设置——请在项目根 .env 配置（见 .env.example）}"
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
    command: celery -A backend worker -B -l info -c 1
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

**STATICFILES_DIRS 按目录存在性判断（非 DEBUG）：** 前端构建产物在 `static/frontend/`，`collectstatic` 从 `STATICFILES_DIRS` 收集到 `STATIC_ROOT`（再由 Nginx serve）。生产部署 `collectstatic` 在 `DEBUG=False` 下运行，若用 `if DEBUG` 守卫则 `STATICFILES_DIRS` 为空 → 前端 JS/CSS 收集不到 → SPA 白屏。因此改为 `if (BASE_DIR / 'static').exists()` 守卫：生产能收集到前端产物，全新检出（`static/` 被 gitignore、尚未 build）时目录不存在则不设，避免 `manage.py check` 的 `staticfiles.W004` 警告。

```python
_FRONTEND_STATIC_DIR = BASE_DIR / 'static'
if _FRONTEND_STATIC_DIR.exists():
    STATICFILES_DIRS = [_FRONTEND_STATIC_DIR]
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

部署跨两台机器：**本地构建机** build 前端 + collectstatic（云服务器内存有限，`npm install` 易 OOM），产物 scp 到服务器；**云服务器** `git clone` 源码 → 现场构建镜像 → 跑容器。

### 首次部署

```bash
# === 云服务器 ===
git clone git@github.com:5ME/AiFriends.git ~/ai-friends && cd ~/ai-friends   # 源码：根文件 + backend/ + frontend/
git checkout <branch>
cp .env.example .env   # 填真实值；复用现有 PG 卷时 PG_PASSWORD 须 = 现有 aifriends 用户密码
mkdir -p ssl && openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/aifriends-selfsigned.key -out ssl/aifriends-selfsigned.crt -subj '/CN=115.190.245.146'
sudo systemctl stop nginx   # 停裸机服务（80/443 冲突）

# === 本地构建机 ===
cd frontend && npm install && npm run build && cd ..        # → backend/static/frontend/
cd backend && python manage.py collectstatic --noinput && cd ..   # → backend/staticfiles/
scp -r backend/staticfiles gqyin@115.190.245.146:ai-friends/backend/   # 只传产物（gitignore，不随 clone）

# === 云服务器 ===
docker compose run --rm django python manage.py migrate     # 容器内迁移（宿主机解析不了服务名 postgres）
docker compose up -d --build                                # 现场构建镜像 + 起 5 容器
```

### 更新部署

```bash
# 本地构建机：重建前端 + 传产物
cd frontend && npm run build && cd .. && cd backend && python manage.py collectstatic --noinput && cd ..
scp -r backend/staticfiles gqyin@115.190.245.146:ai-friends/backend/
# 云服务器：拉代码 + 迁移 + 重建重启
cd ~/ai-friends && git pull
docker compose run --rm django python manage.py migrate
docker compose up -d --build
```

> 前端 API base 是 Vite 构建期常量：cloud 模式默认 = `https://115.190.245.146`（=本服务器，同源生效）；换 IP/域名须 `VITE_CLOUD_BASE=https://新地址 npm run build` 重新构建（改 .env/nginx 对已 build 的 JS 无效）。

## 十、文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/Dockerfile` | **新建** | Django + Celery 共用镜像 |
| `docker-compose.yml` | **修改** | 从 2 服务扩到 5 服务 |
| `nginx.conf` | **新建** | Nginx 反代配置（项目根目录） |
| `.dockerignore`（项目根） | **新建** | 排除不用进镜像的文件 |
| `init.sql` | **修改** | 精简为只建 vector 扩展 |
| `backend/backend/settings.py` | **修改** | 加 SECURE_PROXY_SSL_HEADER（2 行） |
| `backend/.env.example` | **修改** | 标注 Docker 环境的 host 差异 |
| `.env.example`（项目根） | **新建** | Docker 部署环境变量模板（compose 读项目根 .env） |
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
| 5 | 2026-06-26 | STATICFILES_DIRS 改为按目录存在性判断（非 DEBUG） | 部署发现：DEBUG=False 时 collectstatic 收集不到前端产物 → SPA 白屏 |
| 6 | 2026-06-26 | 部署流程补 migrate 步骤 + .env 改为项目根 + collectstatic/ssl 顺序明确 | Task 6 code review: 缺 migrate 空库无表、根 .env 缺失、ssl 缺失 nginx 崩溃 |
| 7 | 2026-06-26 | celery 加 -B 嵌入式 Beat + MEDIA_URL 改读 DJANGO_MEDIA_URL + 修文件清单 | Capstone review: Beat 未运行定时任务永不触发；MEDIA_URL 变量名不匹配致旋钮失效 |
| 8 | 2026-06-26 | POSTGRES_PASSWORD 改 `${PG_PASSWORD:?...}` 必填校验 | PR #31 review: 拒绝原 `:-default` fallback（会致 PG/Django 密码不一致 + 引入默认凭据），改 `:?` 在 up 前 fail-fast |
| 9 | 2026-06-26 | 部署交付模型改为 git clone 源码 + 本地 build 前端 + scp `staticfiles/`（非服务器上 build） | 实际工作流：云服务器 4GiB 内存跑 `npm install` 易 OOM，前端须本地构建 |
| 10 | 2026-06-28 | index.py 生产读 `STATIC_ROOT`（修首页 404）+ 根 .env.example `PG_PASSWORD` 置空（`:?` fail-fast 生效）+ 前端 API base 构建期常量说明 + 同步过时文档 | PR #31 全库 review: 容器无 `static/` 致 `/` 返回 404；非空默认密码绕过 `:?` 校验；spec/plan 多处过时 |
