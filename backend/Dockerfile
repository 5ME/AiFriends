# backend/Dockerfile
FROM python:3.12-slim

# 不缓冲 stdout/stderr（容器日志实时可见）+ 不写 .pyc
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 换国内 apt 源（清华）——服务器在国内，deb.debian.org 慢
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources

# 构建工具（源码安装的依赖兜底）+ curl（Django healthcheck 探测 /api/health/）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Build context 是项目根，COPY 相对 context
COPY requirements.txt .
# 换国内 pip 源（清华）加速安装
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

COPY backend/ .

EXPOSE 8000
CMD ["gunicorn", "--workers", "3", "--graceful-timeout", "30", "--bind", "0.0.0.0:8000", "backend.wsgi:application"]
