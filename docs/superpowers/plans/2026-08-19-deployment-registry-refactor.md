# 部署方式重构（registry）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「本地 build 前端 + scp 静态 + 服务器 build 后端」改为「本地 build 多阶段镜像 → push 阿里云 ACR → 服务器 pull + up」。

**Architecture:** 多阶段 Dockerfile（node 阶段 build 前端 → python 阶段装后端 + collectstatic）；前端静态由 django 通过 whitenoise 服务（去掉 nginx 的 /static/ alias 和 staticfiles bind mount）；默认头像从 media 挪到 static；compose 的 django/celery 改用 `image: ${ACR_IMAGE}`。

**Tech Stack:** Django 6 + whitenoise、Vue 3 + Vite、Docker multi-stage build、阿里云 ACR 个人版。

---

## 文件结构总览

| 文件 | 动作 | 职责 |
|------|------|------|
| `requirements.txt` | 修改 | 增加 `whitenoise` |
| `backend/backend/settings.py` | 修改 | whitenoise 中间件 + `STATIC_URL='/static/'` |
| `backend/web/models/user.py` | 修改 | `DEFAULT_PHOTO` 常量 + `UserProfile.photo_url` 属性 |
| `backend/web/views/utils/photo.py` | 修改 | 从模型导入 `DEFAULT_PHOTO`（消除重复定义） |
| `backend/web/tests/test_user.py` | 新建 | `photo_url` 单元测试 |
| `backend/web/views/...`（9 个文件） | 修改 | `.photo.url` → `.photo_url` |
| `frontend/public/default.png` | 移动 | 默认头像从 `backend/media/user/photos/` 挪来 |
| `backend/Dockerfile` | 重写 | 多阶段构建 |
| `.dockerignore` | 修改 | 前端目录细粒度排除 |
| `docker-compose.yml` | 修改 | `build:` → `image:`，移除 staticfiles 挂载 |
| `nginx.conf` | 修改 | 移除 `/static/` 段 |
| `deploy/build.sh` | 新建 | 本地 build + push |
| `deploy/server-deploy.sh` | 新建 | 服务器 pull + up |
| `服务器部署.md` | 重写 | registry 流程文档 |

---

## Task 1: whitenoise 依赖 + 中间件 + `STATIC_URL`

**Files:**
- Modify: `requirements.txt`
- Modify: `backend/backend/settings.py`

> 先做这一步：`STATIC_URL` 改为绝对路径 `/static/` 是后续 `photo_url`（Task 2）返回正确 URL 的前提。

- [ ] **Step 1: 增加 whitenoise 依赖**

在 `requirements.txt` 末尾追加一行：

```
whitenoise>=6.0
```

安装到当前环境：

Run: `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple whitenoise>=6.0`
Expected: 安装成功。

- [ ] **Step 2: 加中间件 + 改 STATIC_URL**

修改 `backend/backend/settings.py`：

`MIDDLEWARE`（在 `SecurityMiddleware` 之后插入 whitenoise）：

```python
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # 必须尽量靠前
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'web.middleware.request_id.RequestIdMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'web.middleware.rate_limit.RateLimitMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
```

`STATIC_URL`（第 157 行附近）：

```python
STATIC_URL = '/static/'
```

- [ ] **Step 3: 运行全量测试确认不回归**

Run: `cd backend && python -m pytest web/tests/ -v`
Expected: 全部 PASS（whitenoise 在无 STATIC_ROOT 时透传，不影响既有测试）。

- [ ] **Step 4: 提交**

```bash
git add requirements.txt backend/backend/settings.py
git commit -m "feat: 引入 whitenoise + STATIC_URL 改绝对路径" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `UserProfile.photo_url` 属性（TDD）

**Files:**
- Modify: `backend/web/models/user.py`
- Modify: `backend/web/views/utils/photo.py`
- Test: `backend/web/tests/test_user.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/web/tests/test_user.py`：

```python
from web.models.user import DEFAULT_PHOTO


def test_photo_url_default_returns_static(user_profile):
    """默认头像（未上传自定义照片）→ 返回 static URL 而非 media URL"""
    assert user_profile.photo.name == DEFAULT_PHOTO
    assert user_profile.photo_url == '/static/frontend/default.png'
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest web/tests/test_user.py -v`
Expected: 失败——`AttributeError: 'UserProfile' object has no attribute 'photo_url'` 且 `DEFAULT_PHOTO` 未导入。

- [ ] **Step 3: 实现 `photo_url` 属性 + `DEFAULT_PHOTO`**

修改 `backend/web/models/user.py`（顶部 import + 常量 + 属性）：

```python
import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils.timezone import now, localtime

DEFAULT_PHOTO = 'user/photos/default.png'


def photo_upload_to(instance, filename):
    ext = filename.split('.')[-1]
    filename = f'{uuid.uuid4().hex[:16]}.{ext}'
    return f'user/photos/{instance.user_id}_{filename}'


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    photo = models.ImageField(default=DEFAULT_PHOTO, upload_to=photo_upload_to)
    profile = models.TextField(default='谢谢你的关注', max_length=500)
    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(default=now)

    @property
    def photo_url(self):
        if self.photo and self.photo.name != DEFAULT_PHOTO:
            return self.photo.url
        return settings.STATIC_URL + 'frontend/default.png'

    def __str__(self):
        return f'{self.user.username} - {localtime(self.created_at).strftime("%Y-%m-%d %H:%M:%S")}'
```

修改 `backend/web/views/utils/photo.py`，改为从模型导入（消除重复定义）：

```python
import os

from django.conf import settings

from web.models.user import DEFAULT_PHOTO


def remove_old_photo(photo) -> None:
    if photo and photo.name != DEFAULT_PHOTO:
        old_photo_path = settings.MEDIA_ROOT / photo.name
        if old_photo_path.exists():
            os.remove(old_photo_path)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest web/tests/test_user.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/web/models/user.py backend/web/views/utils/photo.py backend/web/tests/test_user.py
git commit -m "feat: UserProfile.photo_url 默认头像返回 static URL" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 默认头像挪进 static + 更新 9 处视图

**Files:**
- Move: `backend/media/user/photos/default.png` → `frontend/public/default.png`
- Modify: 9 个 view 文件（见下方清单）

- [ ] **Step 1: 移动默认头像文件**

Run（项目根）:
```bash
cp backend/media/user/photos/default.png frontend/public/default.png
ls -la frontend/public/default.png
```
Expected: 文件存在，约 433KB。

> 说明：`frontend/public/` 会被 vite 原样拷贝到 `backend/static/frontend/`，collectstatic 后服务为 `/static/frontend/default.png`，与 Task 2 的 `photo_url` 返回值一致。`backend/media/user/photos/default.png` 原文件可保留（老数据兼容）。

- [ ] **Step 2: 更新 9 处视图调用点**

将以下每处的 `...photo.url` 改为 `...photo_url`（`character.author.photo.url` → `character.author.photo_url`；`user_profile.photo.url` → `user_profile.photo_url`；`friend.character.author.photo.url` → `friend.character.author.photo_url`）：

| 文件 | 行 | 旧 | 新 |
|------|----|----|----|
| `backend/web/views/user/account/login.py` | 30 | `user_profile.photo.url` | `user_profile.photo_url` |
| `backend/web/views/user/account/register.py` | 32 | `user_profile.photo.url` | `user_profile.photo_url` |
| `backend/web/views/user/account/get_user_info.py` | 23 | `user_profile.photo.url` | `user_profile.photo_url` |
| `backend/web/views/user/profile/update.py` | 54 | `user_profile.photo.url` | `user_profile.photo_url` |
| `backend/web/views/homepage/index.py` | 42 | `character.author.photo.url` | `character.author.photo_url` |
| `backend/web/views/friend/get_list.py` | 39 | `friend.character.author.photo.url` | `friend.character.author.photo_url` |
| `backend/web/views/friend/get_or_create.py` | 49 | `friend.character.author.photo.url` | `friend.character.author.photo_url` |
| `backend/web/views/create/character/get_list.py` | 45 | `character.author.photo.url` | `character.author.photo_url` |
| `backend/web/views/create/character/get_list.py` | 54 | `user_profile.photo.url` | `user_profile.photo_url` |

> 注意：只改 `author.photo.url` 和 `user_profile.photo.url` 这两类；`character.photo_url`（角色自身头像）已经是属性调用，不要动。

- [ ] **Step 3: 运行相关测试确认不回归**

Run: `cd backend && python -m pytest web/tests/test_auth.py web/tests/test_character.py web/tests/test_homepage.py web/tests/test_friend.py -v`
Expected: PASS（`test_auth.py` 只断言 `"photo" in data`，不校验具体 URL，故改静态 URL 不破坏）。

- [ ] **Step 4: 提交**

```bash
git add frontend/public/default.png backend/web/views/
git commit -m "feat: 默认头像进 static + 视图改用 photo_url" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 多阶段 Dockerfile + `.dockerignore`

**Files:**
- Rewrite: `backend/Dockerfile`
- Modify: `.dockerignore`

- [ ] **Step 1: 重写 `backend/Dockerfile`**

```dockerfile
# backend/Dockerfile — 多阶段构建：前端 + 后端打进同一镜像
# Stage 1: 构建前端
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# VAD 语音识别资源（ort-wasm + silero onnx）在 node_modules 里、被 gitignore，
# 需从 node_modules 复制到 public/vad/，否则全新 build 缺语音识别
RUN mkdir -p public/vad \
    && cp node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded*.wasm public/vad/ \
    && cp node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs public/vad/ \
    && cp node_modules/@ricky0123/vad-web/dist/silero_vad_legacy.onnx public/vad/ \
    && cp node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js public/vad/
ENV VITE_PLATFORM=docker
RUN npm run build

# Stage 2: 后端 + 收集静态
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
COPY backend/ .
COPY --from=frontend /app/backend/static/frontend /app/backend/static/frontend
RUN DJANGO_SECRET_KEY=build-time-only python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["gunicorn", "--workers", "3", "--graceful-timeout", "30", "--bind", "0.0.0.0:8000", "backend.wsgi:application"]
```

- [ ] **Step 2: 修改 `.dockerignore`（细粒度排除前端）**

把原来的 `frontend/` 一行替换为三行（`frontend/node_modules/`、`frontend/public/vad/`、`frontend/dist/`）。最终 `.dockerignore`：

```
# 版本控制 / 文档 / 工具（加速 build context 传输）
.git/
docs/
.codegraph/

# 前端 — node_modules 由 npm ci 重建；VAD 资源由 Dockerfile 从 node_modules 复制
frontend/node_modules/
frontend/public/vad/
frontend/dist/

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

- [ ] **Step 3: 本地 build 验证**

Run（项目根）:
```bash
docker build -t aifriends:test -f backend/Dockerfile .
```
Expected: build 成功，最后能看到 `collectstatic` 输出。若 VAD 复制源路径报错（node_modules 结构变动），按实际路径修正 cp 命令。

- [ ] **Step 4: 验证镜像内含前端 + 静态**

Run:
```bash
docker run --rm aifriends:test ls /app/staticfiles/frontend/assets
docker run --rm aifriends:test ls /app/staticfiles/frontend/vad
```
Expected: 两个目录均列出文件（assets 含 hashed JS/CSS，vad 含 wasm/onnx）。

- [ ] **Step 5: 提交**

```bash
git add backend/Dockerfile .dockerignore
git commit -m "feat: 多阶段 Dockerfile（前端进镜像）+ .dockerignore 调整" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: `docker-compose.yml` 改 `image:` + `nginx.conf` 去掉 /static/

**Files:**
- Modify: `docker-compose.yml`
- Modify: `nginx.conf`

- [ ] **Step 1: 改 compose 的 django/celery 为 `image:`，移除 staticfiles 挂载**

`django` 服务：把 `build:` 块替换为 `image: ${ACR_IMAGE:-aifriends:latest}`，并删除 volumes 里的 `./backend/staticfiles:/app/staticfiles` 行：

```yaml
  django:
    image: ${ACR_IMAGE:-aifriends:latest}
    container_name: ai-friends-web
    command: gunicorn --workers 3 --graceful-timeout 30 --bind 0.0.0.0:8000 backend.wsgi:application
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
    healthcheck:
      test: ["CMD", "python", "-c", "import socket; socket.create_connection(('127.0.0.1', 8000), 3).close()"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 30s
```

`celery` 服务：把 `build:` 块替换为 `image: ${ACR_IMAGE:-aifriends:latest}`：

```yaml
  celery:
    image: ${ACR_IMAGE:-aifriends:latest}
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
```

`nginx` 服务：删除 volumes 里的 `./backend/staticfiles:/app/staticfiles:ro` 行（保留 media 和 ssl）：

```yaml
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
      - ./backend/media:/app/media:ro
      - ./ssl:/etc/nginx/ssl:ro
    restart: unless-stopped
```

- [ ] **Step 2: `nginx.conf` 移除两个 `/static/` 段**

删除 `location /static/ { ... }` 和 `location /static/frontend/vad/ { ... }` 两段（`/static/` 现由 django+whitenoise 服务）。最终：

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

    client_max_body_size 10m;

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

        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

- [ ] **Step 3: 验证 compose 配置合法**

Run（项目根）:
```bash
docker compose config --quiet
```
Expected: 无报错输出（`--quiet` 仅在配置非法时报错）。

- [ ] **Step 4: 提交**

```bash
git add docker-compose.yml nginx.conf
git commit -m "feat: compose 改 image: 拉取 + nginx 静态改走 whitenoise" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: 部署脚本

**Files:**
- Create: `deploy/build.sh`
- Create: `deploy/server-deploy.sh`

- [ ] **Step 1: 创建 `deploy/build.sh`（本地 build + push）**

```bash
#!/usr/bin/env bash
set -euo pipefail
ACR_IMAGE="${ACR_IMAGE:?请在环境变量或 .env 中设置 ACR_IMAGE（完整镜像名，含 tag）}"
docker build -t "$ACR_IMAGE" -f backend/Dockerfile .
docker push "$ACR_IMAGE"
echo "已推送: $ACR_IMAGE"
```

- [ ] **Step 2: 创建 `deploy/server-deploy.sh`（服务器 pull + up）**

```bash
#!/usr/bin/env bash
set -euo pipefail
docker compose pull
docker compose up -d
docker compose ps
```

- [ ] **Step 3: 加可执行权限**

Run（项目根）:
```bash
chmod +x deploy/build.sh deploy/server-deploy.sh
```

- [ ] **Step 4: 提交**

```bash
git add deploy/build.sh deploy/server-deploy.sh
git commit -m "feat: 部署脚本 build.sh + server-deploy.sh" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: 重写 `服务器部署.md`

**Files:**
- Rewrite: `服务器部署.md`

- [ ] **Step 1: 用 registry 流程重写部署文档**

把 `服务器部署.md` 全文替换为以下内容（覆盖：架构、ACR 一次性准备、本地 build/push、服务器 pull/up、更新发版）：

```markdown
# 服务器部署（Registry + Docker Compose）

`docker compose pull && up -d` 一键启动全栈：PostgreSQL 17 + Redis 7 + Django/gunicorn + Celery(+Beat) + Nginx。
镜像在本地 build 后推送到阿里云 ACR，服务器只拉取、不 build。

## 架构

- **本地构建机**：`docker build`（多阶段，前端打进镜像）→ `docker push` 到阿里云 ACR。
- **云服务器（阿里云 ECS，2GB）**：`docker compose pull` → `up -d`。不跑 npm、不 build 镜像。

## 一次性准备

### 1.（阿里云控制台）创建 ACR 个人版实例
- 地域选 **华东2（上海）**（与 ECS 同地域，才能走 `-vpc` 内网）。
- 设置 Registry 登录密码；创建命名空间（如 `gqyin-sh`）、私有镜像仓库（如 `gqyin-docker`）。
- 记下：登录名、密码、公网域名、`-vpc` 内网域名。

### 2.（本地）登录 ACR
```bash
docker login --username=<登录名> crpi-xxxx.cn-shanghai.personal.cr.aliyuncs.com
```

### 3.（服务器）拉源码 + 配环境
```bash
git clone ... && cd AiFriends && git checkout <分支>
cp .env.example .env && vim .env     # 密钥 + ACR_IMAGE + ALLOWED_HOSTS/CORS/MEDIA_URL
mkdir -p ssl && openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/aifriends-selfsigned.key -out ssl/aifriends-selfsigned.crt -subj '/CN=<服务器IP>'
```

`.env` 里 `ACR_IMAGE` 示例（服务器在同地域时可用 `-vpc` 内网域名）：
```
ACR_IMAGE=crpi-xxxx-vpc.cn-shanghai.personal.cr.aliyuncs.com/gqyin-sh/gqyin-docker:latest
```

## 发版

### 本地（build + push）
```bash
ACR_IMAGE=crpi-xxxx.cn-shanghai.personal.cr.aliyuncs.com/gqyin-sh/gqyin-docker:latest ./deploy/build.sh
```

### 服务器（pull + up）
```bash
docker login --username=<登录名> crpi-xxxx-vpc.cn-shanghai.personal.cr.aliyuncs.com
./deploy/server-deploy.sh
```

## 迁移（首次）
```bash
docker compose run --rm django python manage.py migrate
docker compose up -d
```

## 常用运维
```bash
docker compose ps / logs -f / restart <service> / down
```

## 注意事项
- 镜像在本地 build，服务器只 pull（2GB 内存不 build 前端）。
- 默认头像已进 static（随镜像），无需再 scp media 里的 default.png。
- `.env`（密钥）、`ssl/`（自签证书）不进镜像，在服务器上生成。
- media（用户上传）仍为 bind mount，全新部署为空属正常。
```

- [ ] **Step 2: 提交**

```bash
git add 服务器部署.md
git commit -m "docs(deploy): 重写部署文档为 registry 流程" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## 最终验收（全流程）

- [ ] 本地 `./deploy/build.sh` 成功 build + push 到 ACR。
- [ ] 服务器 `./deploy/server-deploy.sh` 后 `docker compose ps` 全 healthy。
- [ ] 浏览器访问：首页数据加载、默认头像显示、语音功能可初始化（无 404、无 127.0.0.1 请求）。
- [ ] 后端全量测试通过：`cd backend && python -m pytest web/tests/ -v`。
