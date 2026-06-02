# ============================================================
# AI Friends 应用镜像
#
# 这个镜像同时用于两个服务（docker-compose 中定义）：
#   web:           gunicorn backend.wsgi
#   celery-worker: celery -A backend worker
#
# 其他服务用公开镜像，不需要 Dockerfile：
#   PostgreSQL + pgvector → pgvector/pgvector:pg17
#   Redis                  → redis:7-alpine
#   Nginx                  → nginx:alpine
# ============================================================

# ── Stage 1: 构建前端 ──────────────────────────────────────
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend

# 利用 Docker 缓存层：先装依赖，再拷源码
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build
# 产物位置：/app/backend/static/frontend/（vite.config.js 配置的 outDir）

# ── Stage 2: 后端应用 ──────────────────────────────────────
FROM python:3.12-slim
WORKDIR /app

# 系统依赖（psycopg2 需要 libpq）
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 后端代码
COPY backend/ .

# 前端构建产物（从 Stage 1 拷贝）
COPY --from=frontend-build /app/backend/static/frontend /app/static/frontend

# 收集 Django 静态文件
RUN python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "--workers", "3", "--bind", "0.0.0.0:8000", "backend.wsgi:application"]
