#!/usr/bin/env bash
# 服务器部署脚本 — 幂等：首次部署与后续发版通用
# pull → migrate（无待应用迁移则秒过）→ seed_builtins（音色/SystemPrompt/可选超管）
# → up -d → ps
set -euo pipefail
docker compose pull
docker compose run --rm django python manage.py migrate --noinput
docker compose run --rm django python manage.py seed_builtins
docker compose up -d
# django 容器重建后 IP 可能变化，nginx 启动时已缓存旧 IP → 重启以重新解析
docker compose restart nginx
docker compose ps
