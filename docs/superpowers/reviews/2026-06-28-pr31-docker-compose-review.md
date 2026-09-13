# PR #31 Review: Docker Compose 全栈部署

> Review date: 2026-06-28  
> Branch: `feature/gqyin/p1-d1-docker-compose`  
> Scope: code + deployment docs for P1-D1 Docker Compose rollout

## Summary

当前不需要额外信息才能完成 review。用户补充的 WSL 现状很关键：旧设计已经在 `/home/ygq/ai-friends` 通过 Docker Compose 启动了 `pgvector` 和 `redis`，因此新 PR 的迁移路径不是空库初始化，而是复用现有 container/volume。

整体方向可行，但我建议 **Request changes**。主要原因是新容器镜像/挂载路径会导致 SPA 首页无法加载；同时根 `.env.example` 的默认数据库密码会在现有 PG 卷迁移场景下误导配置。

## Findings

### P1: Docker 部署后首页会 404

`backend/web/views/index.py` 仍从 `settings.BASE_DIR / 'static' / 'frontend' / 'index.html'` 读取 SPA 入口：

- `backend/web/views/index.py:6`

但 PR 的 Docker 构建与部署流程不会把这个路径带进容器：

- `.dockerignore:15` 排除了 `backend/static/`
- `docker-compose.yml:49` 只把 `./backend/staticfiles` 挂载到 `/app/staticfiles`
- `服务器部署.md:72` 只 scp `backend/staticfiles`
- `nginx.conf:39-44` 对 `/` 代理到 Django，而不是直接 serve `index.html`

结果是访问 `https://<server>/` 时，Nginx 会把请求转给 Django，Django 在容器内查找 `/app/static/frontend/index.html`，该文件不存在，于是返回 `404 前端构建文件不存在`。这会破坏“全栈一键启动”最核心的验收项。

建议修复方式二选一：

1. 让 `index.py` 在生产/Docker 路径下读取 `STATIC_ROOT / 'frontend' / 'index.html'`，即 `/app/staticfiles/frontend/index.html`。
2. 或者把 `backend/static` 也作为构建产物传到服务器并挂载到 `/app/static`，但这会让 `static` 与 `staticfiles` 两套产物并存，部署心智更复杂。

我更建议方案 1，因为 PR 已经明确把 `collectstatic` 产物作为 Nginx/Docker 的静态资源来源。

### P2: 根 `.env.example` 的默认 `PG_PASSWORD` 会误导现有 PG 卷迁移

旧 `origin/master:init.sql` 创建过：

```sql
CREATE USER aifriends WITH PASSWORD 'aifriends001#';
CREATE DATABASE aifriends OWNER aifriends;
```

用户补充当前服务器已经按旧设计启动过 PG/Redis，因此 `postgres-data` volume 已存在。Postgres 官方镜像只在首次初始化空数据目录时使用 `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`；复用已有 volume 时，这些变量不会修改已有用户密码。

当前 PR 新增的根 `.env.example` 写了：

- `.env.example:17` `PG_PASSWORD=change_me_strong_password`

而 Compose 只校验非空：

- `docker-compose.yml:8` `${PG_PASSWORD:?PG_PASSWORD 未设置...}`

这会导致一个高概率迁移失败路径：部署者 `cp .env.example .env` 后忘记改密码，Compose 校验通过，但 Django/Celery 使用 `change_me_strong_password` 连接旧库，实际旧用户密码仍是 `aifriends001#` 或服务器当前 `backend/.env` 里的值，最终应用连不上数据库。

建议：

- 把根 `.env.example` 改为 `PG_PASSWORD=`，让 fail-fast 机制真正生效。
- 保留 `服务器部署.md:56` 的“复用现有 PG 卷必须填旧密码”说明；这段说明是正确且必要的。

### P2: 部署文档没有说明前端 API base 是构建期写死的

`frontend/src/js/config/config.js` 的生产默认值是：

- `frontend/src/js/config/config.js:10` build 默认 `platform = 'cloud'`
- `frontend/src/js/config/config.js:12` `CLOUD_BASE = import.meta.env.VITE_CLOUD_BASE || 'https://115.190.245.146'`
- `frontend/src/js/config/config.js:31-32` API/VAD URL 使用 `CLOUD_BASE`

但部署文档只写了：

- `服务器部署.md:70` `cd frontend && npm install && npm run build && cd ..`

如果后续换服务器 IP/域名，或希望 Docker Compose 同源部署，构建出来的前端会请求错误的 API base。因为这是 Vite 构建期常量，改 `.env` 或 Nginx 不会修复已经 build 的 JS。

建议在 `服务器部署.md` 和 spec 的部署流程里明确其中一种策略：

- 固定云 IP/域名部署：`VITE_CLOUD_BASE=https://<server-ip-or-domain> npm run build`
- Docker 同源部署：`VITE_PLATFORM=docker npm run build`

如果目标是 Nginx 同源反代，我更建议使用 `VITE_PLATFORM=docker`，这样前端请求空 base URL，后续换 IP/域名不需要重写 API base。

### P3: 相关文档存在过时/自相矛盾描述

这些不一定阻断部署，但会影响后续按文档执行：

- `docs/superpowers/specs/2026-06-26-p1-d1-docker-compose-design.md:101-125` 的 `.dockerignore` 片段仍是旧语义，和实际根目录 `.dockerignore` 不一致。
- `docs/superpowers/plans/2026-06-26-p1-d1-docker-compose.md:671` 仍写“当前 `celery worker` 不含 `-B`”，但当前 `docker-compose.yml:70` 已经是 `celery -A backend worker -B -l info -c 1`。
- `docs/superpowers/plans/2026-06-26-p1-d1-docker-compose.md:7` 仍写“8 个文件变更（3 新建、5 修改）”，但实际 PR 还新增了根 `.env.example`，文件清单也已变为 9 个关键文件。

建议同步文档，避免后续 agent 或人工按过时计划执行。

## Positive Notes

- `POSTGRES_PASSWORD` 从默认 fallback 改为 `${PG_PASSWORD:?...}` 是正确方向；只需要配合空的 example 值才能真正 fail-fast。
- Django healthcheck 改为 socket liveness，避免 `/api/health/` 的 Celery 检查拖垮启动顺序，这个判断合理。
- `client_max_body_size 10m`、SSE `proxy_buffering off`、`proxy_read_timeout 300s` 都符合当前上传和聊天流需求。
- `SECURE_PROXY_SSL_HEADER` 只在 `DEBUG=False` 设置，适合 Nginx HTTPS 反代场景。

## Verification

已完成：

- 对比 `origin/master...HEAD` diff。
- 阅读并交叉检查 Dockerfile、Compose、Nginx、Django settings、`.env.example`、`init.sql`、部署文档和两份 superpowers 文档。
- 用 CodeGraph 检查相关 Django settings、health endpoint、Redis/rate-limit 代码上下文。
- 对比旧 `origin/master:docker-compose.yml` 与 `origin/master:init.sql`，确认旧 PG 初始化密码与现有 volume 迁移风险。

未完成：

- 本地 Windows 环境没有可用 Docker CLI，`docker compose config` 无法直接运行。
- 当前 Codex 环境无法访问 WSL 发行版，所以不能直接读取 `/home/ygq/ai-friends` 的实际 `docker compose ps/config`。
- 当前 Python 环境未安装 Django，`python backend/manage.py check` 未能运行。

建议合并前至少在 WSL 或服务器执行：

```bash
cd /home/ygq/ai-friends
docker compose config
docker compose run --rm django python manage.py check
docker compose run --rm django python manage.py migrate
docker compose up -d --build
curl -k https://localhost/
curl -k https://localhost/api/health/
```

其中 `curl -k https://localhost/` 应重点验证不再返回 `前端构建文件不存在`。
