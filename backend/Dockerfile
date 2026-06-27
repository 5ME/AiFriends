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
