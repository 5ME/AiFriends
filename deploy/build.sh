#!/usr/bin/env bash
set -euo pipefail
ACR_IMAGE="${ACR_IMAGE:?请在环境变量或 .env 中设置 ACR_IMAGE（完整镜像名，含 tag）}"
docker build -t "$ACR_IMAGE" -f backend/Dockerfile .
docker push "$ACR_IMAGE"
echo "已推送: $ACR_IMAGE"
