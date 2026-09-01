# backend/Dockerfile — 多阶段构建：前端 + 后端打进同一镜像
# Stage 1: 构建前端
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --registry=https://registry.npmmirror.com
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
RUN pip install --timeout 300 --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --extra-index-url https://mirrors.aliyun.com/pypi/simple/ \
    -r requirements.txt
COPY backend/ .
COPY --from=frontend /app/backend/static/frontend /app/backend/static/frontend
RUN DJANGO_SECRET_KEY=build-time-only python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["gunicorn", "--workers", "3", "--graceful-timeout", "30", "--bind", "0.0.0.0:8000", "backend.wsgi:application"]
