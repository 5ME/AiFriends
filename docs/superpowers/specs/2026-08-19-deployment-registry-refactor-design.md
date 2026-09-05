# 部署方式重构 — 设计文档（spec）

> 目标：把当前「本地 build 前端 + scp 静态 + 服务器 build 后端」的 13 步手工部署，收敛为
> 「**本地 build 完整镜像 → push 阿里云 ACR → 服务器 pull + up**」的 registry 流程。
> 选型结论：**registry（阿里云 ACR 个人版）+ 本地 build + push + 多阶段镜像（前端打进镜像）**。

---

## 1. 背景与目标

### 1.1 现状问题

现行部署（D1）跨两台机器、约 13 步，且有三处文档未覆盖的暗坑：

1. 前端 `npm run build` 的结果靠 scp，`VITE_PLATFORM` 错一次全盘指向 127.0.0.1，无校验。
2. 默认头像 `default.png` 是 gitignore 的 media 文件，全新部署必 404。
3. bind mount 目录被 Docker 以 root 建，非 root 用户 scp 权限拒绝。

### 1.2 目标

- 服务器端零 build、零 scp：`docker compose pull && up -d` 两个动作完成部署。
- 前端 build 一次性固化进镜像，`VITE_PLATFORM=docker` 在 build 期写死，不可能错。
- 全新服务器按文档操作即可跑通，无暗坑。

### 1.3 前提

- 服务器：阿里云 ECS，**2 vCPU / 2GB**，`linux/amd64`，已装 Docker + Compose v2。
- 镜像仓库：阿里云 ACR **个人版**（免费，见下已核实事实）。
- 本地构建机：Windows，装有 Docker Desktop + Node + Python。

### 1.4 ACR 个人版已核实事实（依据阿里云官方文档 + AI 助理）

| 项 | 结论 |
|----|------|
| 费用 | 免费（公测限额免费，拉取/上传均免费，无 SLA） |
| 配额 | 3 命名空间 + 公开/私有仓库各 300 |
| 内网 | 同地域 ECS 用 `-vpc` 域名走内网，无需 PrivateZone/绑定 VPC |
| 认证 | 新实例（2024-09-04 后）**不支持免密拉取**，须 `docker login`（RAM 子账号 + 密码） |
| 域名格式 | 以公告 `crpi-xxxx-vpc.{region}.personal.cr.aliyuncs.com` 为准，实际以控制台显示为准 |
| 带宽 | 共享、QPS 不保障，并发 >10 或频繁拉会 `TOOMANYREQUESTS` |

---

## 2. 目标架构

```
本地构建机（Windows）                阿里云 ACR（同地域）          服务器 ECS（2GB）
──────────────                     ──────────────            ──────────────
docker build（多阶段：含前端）
docker push  ───────────────────▶  crpi-xxxx.personal.cr...
                                        │
                                        │ docker compose pull（-vpc 内网，增量）
                                        ▼
                                   docker compose up -d
                                   （postgres + redis + django/gunicorn
                                     + celery + nginx，5 容器）
```

- 镜像内包含：后端 + 前端静态产物 + 默认头像。
- 服务器 git clone 只用来拿 `docker-compose.yml` + `nginx.conf`（配置文件走版本库）。
- `.env`（密钥）、`ssl/`（自签证书）在服务器上生成/填写，不进镜像、不进 git。

---

## 3. 详细设计

### 3.1 多阶段 Dockerfile（`backend/Dockerfile` 重写）

```dockerfile
# ── Stage 1：构建前端 ──
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_PLATFORM=docker          # 关键：同源模式写死在 build 期
RUN npm run build                 # vite 输出到 ../backend/static/frontend/

# ── Stage 2：后端 + 收集静态 ──
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev curl \
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

要点：
- `VITE_PLATFORM=docker` 在 Stage 1 里写死，杜绝错误模式。
- `collectstatic` 在 build 期完成（`DJANGO_SECRET_KEY=build-time-only` 仅为让 DEBUG=False 的 settings 能加载，不持久化进镜像）。
- 镜像内 `STATIC_ROOT=/app/staticfiles` 已含前端产物 + admin 静态 + 默认头像。

### 3.2 静态文件服务：引入 whitenoise

前端静态不再走「服务器 scp + nginx alias」，改为**由 django 通过 whitenoise 直接服务**，镜像自包含、无共享 bind mount。

改动：
1. `requirements.txt` 增加 `whitenoise`。
2. `settings.py`：`MIDDLEWARE` 在 `SecurityMiddleware` 之后加入
   `whitenoise.middleware.WhiteNoiseMiddleware`；`STATIC_URL` 由 `'static/'` 改为 `'/static/'`
   （绝对路径，确保 whitenoise 匹配 `/static/...` 请求）。
3. `nginx.conf` 删除 `/static/` 的 `alias` 段；`/` 统一 `proxy_pass http://django:8000`。
   `/media/` 保留 `alias /app/media/`（用户上传数据，仍为 bind mount）。
4. `docker-compose.yml` 移除 `staticfiles` 的 bind mount（django 与 nginx 均不再需要）。

> 为什么选 whitenoise 而非「nginx 直接服务静态」：前者静态随镜像走、无共享卷、无启动顺序依赖、无 root 属主问题，实现最简单。个人单用户场景下，静态经 gunicorn/whitenoise 的性能损耗可忽略。备选方案见 §5。

### 3.3 默认头像挪到 static（消除 media 暗坑）

现状：`UserProfile.photo = ImageField(default='user/photos/default.png')`，指向 gitignore 的 `media/user/photos/default.png` → 全新部署 404。

改动：
1. 把 `backend/media/user/photos/default.png`（433KB）移到 `frontend/public/default.png`
   （vite 会原样拷到 `backend/static/frontend/default.png` → 服务为 `/static/frontend/default.png`）。
2. 给 `UserProfile` 增加 `photo_url` 属性（对齐 `Character.photo_url` 的既有模式）：

```python
DEFAULT_PHOTO = 'user/photos/default.png'   # 与 web/views/utils/photo.py 统一

@property
def photo_url(self):
    if self.photo and self.photo.name != DEFAULT_PHOTO:
        return self.photo.url                       # 用户自传头像 → media
    return settings.STATIC_URL + 'frontend/default.png'   # 默认 → static
```

3. 把 9 处 `user_profile.photo.url` / `character.author.photo.url` 调用点改为 `...photo_url`：

   - `views/user/account/login.py`
   - `views/user/account/register.py`
   - `views/user/account/get_user_info.py`
   - `views/user/profile/update.py`
   - `views/homepage/index.py`
   - `views/friend/get_list.py`
   - `views/friend/get_or_create.py`
   - `views/create/character/get_list.py`
   - `views/create/character/get_single.py`

> 说明：DB 里存量行的 `photo.name` 仍是 `'user/photos/default.png'`（哨兵值），无需迁移；仅 URL 解析方式变化。`remove_old_photo` 的 `DEFAULT_PHOTO` 判断保持兼容。

### 3.4 docker-compose.yml 改动

- `django` / `celery` 的 `build:` 改为 `image: ${ACR_IMAGE:-aifriends:latest}`（引用仓库镜像，不再现场 build）。
- 移除 `nginx` 与 `django` 的 `staticfiles` bind mount。
- 保留：`postgres-data` / `redis-data` named volume；`media` / `logs` bind mount；`ssl` 挂载进 nginx。
- `depends_on` / healthcheck / 端口映射保持不变。

`.env`（服务器）新增一行 `ACR_IMAGE`（**已确定的实际值**）：

```
ACR_IMAGE=crpi-2ltqkeifvac3nlun.cn-shanghai.personal.cr.aliyuncs.com/gqyin-sh/gqyin-docker:latest
```

> 实际参数：命名空间 `gqyin-sh`、仓库 `gqyin-docker`、登录名 `me不想家`、地域 `cn-shanghai`。
> 专有网络域名（服务器内网拉取，可选）：`crpi-2ltqkeifvac3nlun-vpc.cn-shanghai.personal.cr.aliyuncs.com/gqyin-sh/gqyin-docker`。

### 3.5 部署脚本

**`deploy/build.sh`（本地）**：

```bash
#!/usr/bin/env bash
set -euo pipefail
ACR_IMAGE="${ACR_IMAGE:?请在环境或 .env 中设置 ACR_IMAGE}"
docker build -t "$ACR_IMAGE" -f backend/Dockerfile .
docker push "$ACR_IMAGE"
```

**`deploy/server-deploy.sh`（服务器）**：

```bash
#!/usr/bin/env bash
set -euo pipefail
docker compose pull
docker compose up -d
docker compose ps
```

### 3.6 全新服务器部署流程（收敛后）

```bash
# 一次性（服务器）
git clone ... && cd AiFriends && git checkout <分支>
cp .env.example .env && vim .env        # 密钥 + ACR_IMAGE + ALLOWED_HOSTS/CORS/MEDIA_URL
mkdir -p ssl && openssl req ...          # 自签证书

# 一次性（本地）
docker login crpi-xxxx...personal.cr.aliyuncs.com   # RAM 子账号 + 密码

# 每次发版（本地）
./deploy/build.sh                        # build + push

# 每次发版（服务器）
./deploy/server-deploy.sh                # pull + up
```

---

## 4. 待解决项（实现阶段需逐一确认，勿盲信）

1. **VAD 语音识别模型文件（~85MB，已确认：手工拷贝）**：`frontend/public/vad/` 被 gitignore，
   内容是 `ort-wasm-*.wasm` + `silero_vad_legacy.onnx`，来自 node_modules 的 `onnxruntime-web` +
   `@ricky0123/vad-web`，当前**手工从 node_modules 拷入、无脚本**。
   **多阶段 build 必须在 Stage 1 里从 node_modules 复制这些文件到 `public/vad/`**（copy 的确切源路径实现时确认），否则全新 build 缺语音识别。
2. ~~STATIC_URL 无前导斜杠~~ ✅ 已定：改为 `/static/`（见 §3.2）。
3. ✅ 已定 — ACR 实际域名：公网 `crpi-2ltqkeifvac3nlun.cn-shanghai.personal.cr.aliyuncs.com`；内网 `crpi-2ltqkeifvac3nlun-vpc.cn-shanghai.personal.cr.aliyuncs.com`（地域 `cn-shanghai`）。
4. **collectstatic 在 build 期是否需 DB**：理论不连 DB，但若某 app ready() 里连了 DB 需处理（实现时验证）。

---

## 5. 备选方案（已考虑、未采用）

| 方案 | 说明 | 未采用原因 |
|------|------|-----------|
| 服务器上 build 多阶段镜像 | 单命令 `up --build` | 2GB 内存跑 `npm install` 易 OOM |
| save/load 传 tar | 本地 build → `docker save` → scp → `load` | 每次传全量 1~2GB，无增量 |
| nginx 直接服务静态（共享 named volume + entrypoint copy） | 保留 nginx alias | 需共享卷 + 启动 copy 逻辑，比 whitenoise 复杂 |
| GitHub Actions build + push | push 代码即上线 | 境外 runner 跨境推 1~2GB 到国内 ACR，慢/易失败 |

---

## 6. 验收标准

1. 本地 `docker build -f backend/Dockerfile .` 成功，镜像内含前端产物。
2. 全新 ECS 按 §3.6 操作后，浏览器访问首页：数据正常加载、默认头像显示、语音功能可初始化。
3. 服务器全程无 `npm install`、无 `docker build`、无 scp。
4. 二次发版只改前端代码，服务器 `pull` 仅拉变更层（增量，非全量）。
5. 现有 pytest 套件（204 tests）全部通过（默认头像改动不破坏接口契约）。

---

## 7. 范围外（YAGNI）

- 域名 + Let's Encrypt 正式证书（当前 IP + 自签，后续另议）。
- 企业版 ACR / 多区域同步 / P2P 分发。
- 自动部署（GitHub Actions / 云效）—— 留作后续升级。
- 镜像 tag 版本化 + 回滚（先用 `latest`，需要时再引入 git-SHA tag）。
- 容器非 root 运行（bind mount 属主问题通过「静态不再 bind mount」规避，media/logs 用一次性 chown 处理）。
