# Spec Review: 部署方式重构（ACR Registry）设计文档

> Review date: 2026-08-19
> Spec: `docs/superpowers/specs/2026-08-19-deployment-registry-refactor-design.md`
> Scope: 设计文档审阅（实现前），所有结论均对照当前代码逐条验证

## Summary

方向与选型我完全同意：registry + 本地 build + 多阶段镜像（前端打进镜像）+ whitenoise 自包含静态，是针对 2GB 单机、单人场景的正确收敛；§5 备选方案的排除理由也都成立。但 spec 有 **4 个"照文档实施会直接卡住"的阻断项**和 **3 个设计决策缺口**，建议 **Request changes**，补齐后再进入实现。多数问题我在审阅中已给出可直接采用的修法。

---

## Findings

### P0-1: `.dockerignore` 排除了整个 `frontend/`，Stage 1 的 COPY 会直接 build 失败

`.dockerignore:5` 有 `frontend/` 整行排除。spec §3.1 Stage 1 的
`COPY frontend/package.json frontend/package-lock.json ./` 和 `COPY frontend/ ./`
在 context 里根本找不到文件，第一步就失败。**spec 全文没有提到 .dockerignore 的任何改动。**

修法（必须三条同时做）：

1. 删除 `.dockerignore:5` 的 `frontend/` 行；
2. 新增排除 `frontend/node_modules/`——这是**必须**的：宿主机（Windows）的 node_modules 若被 COPY 进 Linux 镜像，会覆盖 `npm ci` 装的 Linux 依赖（原生二进制），且 context 会膨胀几百 MB；
3. 新增排除 `frontend/public/vad/`——防止宿主机上的陈旧/损坏拷贝被烤进镜像（见 P0-2，vad 应由容器内生成）。

### P0-2: VAD 文件的拷贝方式与 context 过滤矛盾，且源路径已可确定

spec §4.1 说"多阶段 build 必须在 Stage 1 里从 node_modules 复制这些文件（copy 的确切源路径实现时确认）"。如果按字面理解成 Dockerfile 的 `COPY frontend/node_modules/...`，会与 P0-1 中"node_modules 必须被 context 排除"直接冲突——这是自相矛盾的。

正确做法：**在镜像内拷贝，不经过 build context**——Stage 1 `RUN npm ci` 之后用 `RUN cp`：

```dockerfile
RUN mkdir -p public/vad \
 && cp node_modules/@ricky0123/vad-web/dist/silero_vad_legacy.onnx \
       node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js \
       node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm \
       node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs \
       node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.asyncify.wasm \
       node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.jsep.wasm \
       node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.jspi.wasm \
       public/vad/
```

源路径已在本机 node_modules 逐一核实，与现有 `frontend/public/vad/` 的 7 个文件完全吻合：

| 源文件 | 大小 |
|--------|------|
| `@ricky0123/vad-web/dist/silero_vad_legacy.onnx` | 1,807,522 |
| `@ricky0123/vad-web/dist/vad.worklet.bundle.min.js` | 2,480 |
| `onnxruntime-web/dist/ort-wasm-simd-threaded.wasm` | 12,361,745 |
| `onnxruntime-web/dist/ort-wasm-simd-threaded.mjs` | 24,274 |
| `onnxruntime-web/dist/ort-wasm-simd-threaded.asyncify.wasm` | 27,190,919 |
| `onnxruntime-web/dist/ort-wasm-simd-threaded.jsep.wasm` | 25,014,754 |
| `onnxruntime-web/dist/ort-wasm-simd-threaded.jspi.wasm` | 16,894,865 |

更优替代：写成 npm `postinstall` 脚本（`node scripts/copy-vad.mjs`，`npm ci` 会自动执行），**顺带修复全新 clone 后本地 dev 也缺 VAD 文件的问题**——`frontend/public/vad/` 被 `.gitignore:14` 忽略，fresh clone 下 `npm run dev` 的语音识别同样是坏的。

### P0-3: compose `build:` → `image:` 直接替换会破坏文档化的本地开发流程

CLAUDE.md 的 Infrastructure 节文档化的是 `wsl docker compose up -d` 启动基础设施，而当前 compose（docker-compose.yml:38、65）用 `build:` 本地构建 django/celery。直接改成 `image: ${ACR_IMAGE:-aifriends:latest}` 后，本地无该镜像 → compose 去 Docker Hub pull `aifriends:latest` → 必然失败，本地全栈起不来。

修法：**`build:` 与 `image:` 并存**，而不是替换：

```yaml
build:
  context: .
  dockerfile: backend/Dockerfile
image: ${ACR_IMAGE:-aifriends:latest}
```

Compose 语义：镜像本地缺失时才构建，存在则直接使用。本地 `up -d` 构建出 `aifriends:latest` 照常工作；服务器 `pull` 之后镜像存在，永远不会触发 build。零成本兼容两条流程。

### P0-4: ACR 公网域名（push）与 -vpc 域名（pull）无法用一个变量表示

spec 自身存在矛盾：§2 架构图和 §1.4 都强调服务器走 `-vpc` 内网域名增量拉取，但 §3.4 的 `.env` 示例是**公网**域名（`crpi-xxxx.cn-shanghai.personal.cr.aliyuncs.com`）。而 §3.5 build.sh 在本地（VPC 外）push，只能解析公网域名。**单一 `ACR_IMAGE` 无法同时服务两端**——本地 push 打 -vpc 域名会解析失败；服务器用公网域名 pull 则放弃内网加速（低带宽 ECS 首次拉 1~2GB，公网可能要很久）。

修法：两个变量：

- `ACR_IMAGE`（公网域名）→ 本地 build.sh push 用；
- `ACR_IMAGE_PULL`（-vpc 域名，同实例同仓库）→ 服务器 compose 引用用：`image: ${ACR_IMAGE_PULL:-${ACR_IMAGE:-aifriends:latest}}`。

注意 `docker login` 凭证按 registry host 分别存储——本地 login 公网 endpoint、服务器 login -vpc endpoint，各登录一次。

---

### P1-1: 服务器端的 `docker login` 在 §3.6 里缺失

spec §1.4 自己核实了"新实例（2024-09-04 后）不支持免密拉取，须 docker login"，但 §3.6 只在"一次性（本地）"列了 login。服务器执行 server-deploy.sh 的 `docker compose pull` 之前**也必须先 login**（且要 login 到 pull 所用的那个域名，见 P0-4）。§3.6 的"一次性（服务器）"清单需要补上这一行。

### P1-2: 全新服务器的基础镜像仍来自 Docker Hub，大陆直连不可用

compose 里 postgres/redis/nginx 仍引用官方镜像（`pgvector/pgvector:pg17`、`redis:7-alpine`、`nginx:1.27-alpine`），`docker compose pull` 会拉全部 5 个镜像。大陆 ECS 直连 Docker Hub registry 基本不可用，这与 spec 的目标"全新服务器按文档操作即可跑通"直接冲突——业务镜像解决了，基础镜像没解决。

两个修法，推荐后者：

1. 服务器一次性配置 registry mirror（`/etc/docker/daemon.json` 的 `registry-mirrors`）——但公共 mirror 名单近年变动频繁、可用性无保障，写进文档有腐烂风险；
2. 本地把 3 个基础镜像 `docker pull` → `docker tag` → push 进同一 ACR 命名空间，compose 改用 `${ACR_REGISTRY:-}pgvector/pgvector:pg17` 之类引用——完全自包含，与"服务器只依赖 ACR"的架构一致。

本地构建机的 `FROM node:20-alpine` / `FROM python:3.12-slim` 同样依赖 Docker Hub——既然 D1 时本地 build 已经成功过（说明本地已配 mirror 或网络可达），把这一步如实写进 §3.6 的一次性设置即可。

### P1-3: gunicorn 默认 30s timeout 会杀死超过 30 秒的 SSE 聊天流

`chat.py:154/178` 用 `StreamingHttpResponse` + 生成器做 SSE。gunicorn **sync worker 在整个响应写完之前不向 master 发送心跳**，master 按 `--timeout`（默认 30s）杀掉"沉默"的 worker。当前 CMD（`backend/Dockerfile:26`、`docker-compose.yml:42`）只设了 `--graceful-timeout 30`，**没有 `--timeout`**——聊天流一旦超过 30 秒（LLM 流式 + TTS 场景极常见）连接就会被掐断。nginx 侧 `proxy_read_timeout 300s`（nginx.conf:51）等于白设。

这是 D1 遗留隐患，本次重写 Dockerfile 正是修复时机：CMD 加 `--timeout 300`（对齐 nginx）或 `--timeout 0`。顺带说明：3 个 sync worker 在流式期间被整占（1 个聊天 = 占 1 个 worker），单人应用可接受，但值得在 spec 里写一句，作为将来换 gthread/gevent 的依据。

---

### P2-1: §3.3 "9 处调用点"的文件清单有事实错误

对照 grep 实测（`\.photo\.url` 全量 11 处）：

- **`create/character/get_single.py` 不在清单里**——它已经用 `character.photo_url`（get_single.py:39），无需任何改动；
- **`create/character/get_list.py` 实际有 2 处**（get_list.py:45 作者头像 + :54 本人头像），spec 算作 1 处；
- **漏了 `web/management/commands/clean_dirty_characters.py:40`** 的 `c.photo.url`（Character 的，管理命令）。顺带换成 `photo_url` 可防无头像角色抛 ValueError。

正确表述：**8 个文件、9 处**（login、register、get_user_info、update、homepage/index、friend/get_list、friend/get_or_create、create/character/get_list×2），另有 1 处管理命令建议顺手改。总数碰巧一致，但实现者照清单改会多改一个文件、漏改一个调用点。

已核实的两个好消息：`Character.photo` **无 default**（character.py:38），角色头像不受 default.png 迁移影响；测试套件无任何 default.png 断言（web/tests 无匹配），验收 #5 的兼容性风险低。

### P2-2: 验收 #4（增量 pull）需要拆层才能真正兑现

spec §3.1 的 `COPY --from=frontend /app/backend/static/frontend ...` 是单层，里面包含 ~83MB 的 VAD 文件。前端任何一次改动都会让整层重建 → 每次发版服务器重传 ~85MB，验收 #4 形同虚设。

修法：把 frontend 产物拆成多个 COPY 层，稳定的放在前面：

```dockerfile
COPY --from=frontend /app/backend/static/frontend/vad/ /app/backend/static/frontend/vad/   # 内容永不变化 → 缓存命中
COPY --from=frontend /app/backend/static/frontend/assets/ /app/backend/static/frontend/assets/  # 每次重传，~几 MB
COPY --from=frontend /app/backend/static/frontend/index.html /app/backend/static/frontend/
COPY --from=frontend /app/backend/static/frontend/favicon.ico /app/backend/static/frontend/
COPY --from=frontend /app/backend/static/frontend/default.png /app/backend/static/frontend/
```

### P2-3: nginx.conf 的 static 删除范围要连 VAD 子块一起

spec §3.2.3 只写了"删除 `/static/` 的 alias 段"，但 nginx.conf:28-32 还有一个独立的 `/static/frontend/vad/` location（`expires off` + immutable 的组合本身就很矛盾），必须一起删。whitenoise 接管后 VAD 缓存策略变化影响很小——`Microphone.vue` 已有 Cache API 缓存（`vad-assets-v1`）兜底。可选：`WHITENOISE_MAX_AGE` + `WHITENOISE_IMMUTABLE_FILE_TEST` 给 `/static/frontend/assets/` 的 hashed 文件加长缓存。

### P2-4: 两个 repo 现状与文档不一致（顺手清理）

1. `backend/web/templates/index.html` 是**死代码**：硬编码 hash `index-DQt15Gx7.js`，与当前构建产物（`index-DBhLRM52.js`）不符；`index.py` 实际直接读构建产物文件（`STATIC_ROOT/frontend/index.html`），模板根本没用上。CLAUDE.md 说"index.py renders templates/index.html"也是错的。留着会误导下一个读代码的人——建议删除模板并更正文档。
2. CLAUDE.md Known technical debt 里"init.sql 是空目录"已过时：现在是 40 字节、被 git 跟踪的普通文件（且 vector 扩展已由 migration 0012 的 RunSQL 兜底，`docker-compose.yml:14` 的挂载可保留也可直接删掉）。

### P2-5: build.sh 不读取根 `.env`

build.sh 的错误消息写"请在**环境或 .env** 中设置 ACR_IMAGE"，但脚本只读环境变量，根 `.env` 是 compose 专属（build.sh 自己不会 source 它）。要么脚本开头 `set -a; source .env 2>/dev/null; set +a`，要么把文档改成明确的 `export ACR_IMAGE=...`。二选一，别让使用者对着 .env 写了值却报 `:?` 错。

---

### P3: 小建议

1. **§4.4 可以划掉了**：已验证无任何 app `ready()` hook（grep 全量无匹配）、无 import 期 DB 访问；`DEBUG=False` 启动只需 `DJANGO_SECRET_KEY`（settings.py:32-38），spec 的 `DJANGO_SECRET_KEY=build-time-only` 处理正确。
2. **`npm ci` 建议加 registry 镜像**（`--registry=https://registry.npmmirror.com`），与 Dockerfile 里 apt/pip 的清华源风格一致；`node:20-alpine` 与 engines `^20.19.0` 之间建议 pin（如 `node:20.19-alpine`）。
3. **server-deploy.sh 加 `docker image prune -f`**：2GB 小盘 ECS，新旧镜像并存 + 悬空镜像会很快占满磁盘。
4. **脚本调用方式写 `bash deploy/xxx.sh`**：Windows git 不保留 exec bit，服务器 clone 后 `./server-deploy.sh` 可能 Permission denied。
5. **新 `UserProfile.photo_url` 属性补单元测试**：现有测试没有 default.png 断言，新逻辑（哨兵值 → static URL）不会被动覆盖，值得主动测。
6. `latest` tag 已在 §7 范围外，尊重 YAGNI；将来引入 git-SHA tag 时，build.sh 里 `docker tag` 一行即可同时打两个 tag。

---

## 已验证正确的部分（正面确认）

以下 spec 结论对照代码全部成立，实现时无需再怀疑：

- **whitenoise 与 Django 6.0.2 兼容**：官方文档明确支持 Django 4.2–6.1 ✓
- **STATIC_URL 现状确实是 `'static/'`**（settings.py:157），改为 `/static/` 必要且低风险（`{% static %}` 自动适配；唯一硬编码路径的模板是死代码，见 P2-4）✓
- **vite `base: '/static/frontend/'` + outDir `../backend/static/frontend`**（vite.config.js:11/23）与 spec §3.1 的 `COPY --from=frontend /app/backend/static/frontend` 路径一致 ✓
- **`index.py` 运行时读 `STATIC_ROOT/frontend/index.html`**（index.py:9-13）——collectstatic 进镜像后该文件存在，SPA 入口与 whitenoise 流程自洽 ✓（PR #31 的修复已在位）
- **`DJANGO_MEDIA_URL` 已有**（.env.example:39，settings.py:167），与默认头像改动无冲突；`backend/media/` 被 .dockerignore:14 排除，用户上传不会进镜像 ✓
- **`default.png` 实测 433,468 字节**，与 spec 的 433KB 一致 ✓
- **UserProfile 哨兵 `'user/photos/default.png'`**（user.py:16）与 `photo.py:5` 的 `DEFAULT_PHOTO` 一致，`remove_old_photo` 兼容性判断不受影响 ✓
- **`Character.photo` 无默认值**，photo_url 已有 ValueError 保护（character.py:44-49），不受迁移影响 ✓
- **whitenoise 中间件位置**（SecurityMiddleware 之后，settings.py:62-73 现状符合）✓
- **compose 现有 staticfiles 挂载点与 spec §3.4 移除清单一一对应**（docker-compose.yml:49/94）✓
- **`docker-compose.yml` 无 profiles**，所有 5 服务共享一个文件——这正是 P0-3 要保 `build:` 的原因 ✓
