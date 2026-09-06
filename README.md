# AI Friends

AI 虚拟角色聊天平台 — 用户可创建 AI 角色并与之进行文字 + 语音聊天，支持长期记忆和 RAG 知识库检索。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Django 6.0 + Django REST Framework + JWT (PostgreSQL 17 + pgvector 0.8) |
| 前端 | Vue 3 (Composition API) + Vite 7 + Pinia + Vue Router 5 |
| UI | Tailwind CSS 4 + daisyUI 5 |
| AI | 阿里云 DashScope（Chat/Memory: deepseek-v4-flash, TTS: cosyvoice-v3-flash, ASR: gummy-realtime-v1） + LangChain/LangGraph |
| 语音 | DashScope TTS (WebSocket) + ASR (WebSocket) + 浏览器端 VAD (Silero VAD / ONNX) |
| 向量存储 | pgvector (1024 维 DashScope text-embedding-v4) |
| 异步任务 | Celery + Redis 7 (Broker + Rate Limit) |
| 部署 | Docker Compose（5 容器）+ 阿里云 ACR registry 拉取 |
| CI | GitHub Actions (209 测试自动运行) |

## 功能

- 创建 / 编辑 / 删除自定义 AI 虚拟角色
- 文字 + 语音双模态聊天，AI 回复支持文字 + 语音同步流式输出
- 聊天上下文长期记忆，每 10 条消息触发 Memory Agent 自动摘要
- RAG 知识库检索（pgvector 余弦距离搜索，支持引用来源标记 + 检索 trace 落库）
- 用户注册登录（JWT access/refresh 双令牌认证，httpOnly cookie）
- 首页角色探索 + 好友关系管理
- 用户文档 RAG 知识库：上传 txt/md/pdf → 异步解析/分块/embedding → pgvector 检索
- Celery + Redis 异步任务队列（Memory Agent 摘要 + 文档处理）
- Redis Lua 原子脚本限流（login/register/chat/asr/upload 分级控制）
- AI API 使用量追踪（LLM/TTS/ASR/Embedding 四类调用）
- 健康检查端点（DB + Redis + Celery 三组件检测）
- Request ID 全链路追踪 + 请求耗时日志
- 前端全局 Toast 通知系统（success/error/warning/info）
- Django Admin 后台管理（文档、角色、好友等）
- 内置音色 + SystemPrompt 一键初始化（`seed_builtins` 幂等命令，随部署自动执行）
- pytest 自动化测试覆盖核心链路（209 个测试）
- GitHub Actions CI（push/PR 自动运行测试）

## 本地开发

日常开发需要启动 **4 个进程**：

### 1. 基础设施（PG + Redis）

```bash
wsl docker compose up -d postgres redis   # 项目根目录执行
```

### 2. 后端（Django）

```bash
cd backend
cp .env.example .env          # 首次：配置 API_KEY 等环境变量
pip install -r ../requirements.txt
python manage.py migrate
python manage.py seed_builtins     # 初始化内置音色 + SystemPrompt（幂等）
python manage.py runserver    # http://127.0.0.1:8000
```

### 3. 前端（Vite HMR）

```bash
cd frontend
npm install                   # 首次
npm run dev                   # http://localhost:5173，API 自动指向 :8000
```

### 4. Celery Worker

```bash
cd backend
celery -A backend worker --loglevel=info --pool=solo
```

> Memory Agent 和文档处理通过 Celery 异步执行，本地开发必须同时运行 Django + Celery。

### 前端 platform 模式

`npm run dev` 和 `npm run build` 自动选择 API 地址，不再需要手动改 `config.js`：

| 命令 | 模式 | API 地址 |
|------|------|---------|
| `npm run dev` | django（默认） | `http://127.0.0.1:8000` |
| `VITE_PLATFORM=vue npm run dev` | vue（纯前端） | `http://127.0.0.1:8000` |
| `VITE_PLATFORM=docker npm run build` | docker（生产，同源） | `''` |
| `$env:VITE_PLATFORM='django'; npm run build` | django（本地打包） | `http://127.0.0.1:8000` |

---

## 部署

部署走「本地 build 镜像 → push 阿里云 ACR → 服务器 pull」的 registry 流程，完整步骤见 `服务器部署.md`。

```bash
# 本地构建机：多阶段 build（前端打进镜像）+ push 到 ACR
ACR_IMAGE=<镜像名> ./deploy/build.sh

# 服务器：一条脚本（pull → migrate → 初始化内置数据 → up -d，幂等）
./deploy/server-deploy.sh
```

> 生产部署前请确保 `.env` 中 `DJANGO_SECRET_KEY` 已设置、`DJANGO_DEBUG=false`、`ACR_IMAGE` 已配置。

---

## 运行测试

```bash
cd backend
python -m pytest web/tests/ -v   # 209 个测试（默认跳过 3 个需 API_KEY 的慢测试）
```

---

## 架构

```
┌─────────────┐     SSE/HTTP      ┌──────────────────────────────────┐
│   Vue 3     │ ◄──────────────► │  Django + DRF (Gunicorn)         │
│   Vite 7    │                   │  ├─ Chat Agent (LangGraph)       │
│   daisyUI 5 │                   │  ├─ Memory Agent (LangGraph)     │
└─────────────┘                   │  ├─ RAG (pgvector)              │
                                  │  ├─ Rate Limit (Redis Lua)      │
                                  │  ├─ API Usage Tracking          │
                                  │  └─ JWT Auth                    │
                                  └──────────┬───────────────────────┘
                                             │
                   ┌─────────────────────────┼─────────────────────────┐
                   │                         │                         │
            ┌──────▼──────┐          ┌──────▼──────┐          ┌──────▼──────┐
            │ PostgreSQL  │          │ Redis 7     │          │ DashScope   │
            │ + pgvector  │          │ (Broker +   │          │ LLM/TTS/ASR │
            └─────────────┘          │  Rate Limit)│          │ + Embedding │
                                     └──────┬──────┘          └─────────────┘
                                            │
                                     ┌──────▼──────┐
                                     │ Celery      │
                                     │ Worker      │
                                     └─────────────┘
```

## 项目结构

```
AiFriends/
│
├── backend/                              # Django 后端项目
│   ├── backend/                          # Django 项目配置
│   │   ├── settings.py                   # 项目设置（DB、JWT、CORS、Rate Limit、Celery 等）
│   │   ├── urls.py                       # 根 URL 配置
│   │   ├── wsgi.py                       # WSGI 入口（Gunicorn）
│   │   ├── asgi.py                       # ASGI 入口
│   │   └── celery.py                     # Celery App 配置
│   │
│   ├── web/                              # 主 Django 应用
│   │   ├── models/                       # 数据模型（6 个文件）
│   │   │   ├── user.py                   #   UserProfile
│   │   │   ├── character.py              #   Character、Voice
│   │   │   ├── friend.py                 #   Friend、Message、SystemPrompt
│   │   │   ├── document.py               #   UserDocument、DocumentChunk (pgvector)
│   │   │   ├── retrieval_trace.py        #   RetrievalTrace（RAG 检索 trace）
│   │   │   └── usage.py                  #   APIUsage（AI 调用用量追踪）
│   │   │
│   │   ├── views/                        # API 视图（文件即视图，无序列化器）
│   │   │   ├── index.py                  #   前端 SPA 入口视图
│   │   │   ├── health.py                 #   健康检查端点（DB + Redis + Celery）
│   │   │   ├── user/account/             #   登录、注册、登出、刷新令牌、获取用户信息
│   │   │   ├── user/profile/             #   个人资料更新
│   │   │   ├── create/character/         #   角色 CRUD + 音色列表
│   │   │   │   └── voice/custom/         #   自定义音色（阿里云 API）
│   │   │   ├── homepage/                 #   首页角色列表
│   │   │   ├── friend/                   #   好友关系管理 + is_friend 检查
│   │   │   │   └── message/
│   │   │   │       ├── chat/             #   LangGraph 聊天 agent + SSE 流式 + TTS
│   │   │   │       ├── asr/              #   语音识别（DashScope WS）
│   │   │   │       └── memory/           #   LangGraph 记忆摘要 agent (Celery)
│   │   │   ├── document/                 #   文档上传/列表/删除 + Celery tasks
│   │   │   └── utils/                    #   图片清理等工具
│   │   │
│   │   ├── middleware/                   # 自定义中间件
│   │   │   ├── request_id.py            #   Request ID + 请求耗时日志
│   │   │   └── rate_limit.py            #   Redis Lua 滑动窗口限流
│   │   │
│   │   ├── documents/                    # RAG 知识库
│   │   │   ├── loaders/                  #   文档加载器（txt/md/pdf）
│   │   │   ├── services/                 #   embedding + chunker
│   │   │   └── utils/                    #   系统知识库增量导入（hash 对比）
│   │   │
│   │   ├── utils/                        # 工具函数
│   │   │   └── usage.py                  #   record_api_usage() (fire-and-forget)
│   │   │
│   │   ├── management/commands/          # Django 管理命令
│   │   │   └── clean_dirty_characters.py #   清理测试残留数据
│   │   │
│   │   ├── tasks.py                      # Celery autodiscover 入口
│   │   ├── admin.py                      # Django Admin 注册
│   │   ├── templates/index.html          # 遗留模板（已不用，SPA 入口为 static/frontend/index.html）
│   │   ├── urls.py                       # 应用 URL 路由 + SPA 兜底路由
│   │   └── apps.py                       # AppConfig
│   │
│   ├── static/frontend/                  # Vite 构建输出（生产）
│   ├── media/                            # 用户上传文件（头像、角色背景等）
│   ├── .env.example                      # 环境变量模板
│   ├── pytest.ini                        # pytest 配置
│   └── manage.py                         # Django CLI 入口
│
├── frontend/                             # Vue 3 SPA 前端
│   ├── src/
│   │   ├── main.js                       # Vue 应用入口
│   │   ├── App.vue                       # 根组件（用户信息拉取 + RouterView + ToastContainer）
│   │   │
│   │   ├── views/                        # 页面视图
│   │   │   ├── homepage/                 #   首页（角色卡片网格 + 无限滚动）
│   │   │   ├── friend/                   #   好友列表页
│   │   │   ├── create/                   #   创作页 + 编辑角色
│   │   │   ├── user/account/             #   登录、注册
│   │   │   ├── user/profile/             #   编辑个人资料
│   │   │   ├── user/space/               #   用户空间
│   │   │   ├── KnowledgeBase.vue         #   知识库页面
│   │   │   └── error/                    #   404 页面
│   │   │
│   │   ├── components/                   # 可复用组件
│   │   │   ├── navbar/                   #   顶部导航栏 + 侧边抽屉 + 用户菜单
│   │   │   │   └── icons/                #     导航图标（含 KnowledgeBaseIcon）
│   │   │   ├── character/                #   角色卡片 + 详情弹窗
│   │   │   │   └── chat_field/           #     聊天模态框（历史、输入、TTS 播放）
│   │   │   ├── knowledge/                #   知识库组件
│   │   │   │   ├── UploadZone.vue        #     拖拽上传
│   │   │   │   └── DocumentCard.vue      #     文档卡片
│   │   │   └── ToastContainer.vue        #   全局 Toast 通知容器
│   │   │
│   │   ├── router/index.js               # Vue Router（路由表 + 登录守卫）
│   │   ├── stores/user.js                # Pinia 用户状态 + JWT 令牌
│   │   ├── composables/                  # 可复用逻辑
│   │   │   ├── useToast.js               #   全局 Toast 状态管理
│   │   │   ├── useImageCropper.js        #   Croppie 图片裁剪
│   │   │   └── useDocumentPolling.js     #   文档处理状态轮询
│   │   └── js/                           # 工具模块
│   │       ├── config/config.js          #   环境自动切换（vue/django/cloud/docker）
│   │       ├── http/api.js               #   Axios 封装 + JWT 自动刷新
│   │       └── http/streamApi.js         #   SSE 流式客户端（AI 聊天）
│   │
│   ├── public/favicon.ico
│   ├── index.html                        # HTML 入口
│   ├── vite.config.js                    # Vite 构建配置
│   └── package.json                      # Node 依赖 + 脚本
│
├── docker-compose.yml                    # PostgreSQL 17 + pgvector + Redis 7
├── .github/workflows/test.yml            # GitHub Actions CI (209 tests)
├── requirements.txt                      # Python 依赖
├── AGENTS.md                             # Codex agent 指令
└── CLAUDE.md                             # Claude Code 项目指南
```

## 已知限制

- [ ] 音色仅支持系统内置，暂不支持用户自定义
- [ ] 未做压测，暂无容量评估数据
- [ ] 无 API 版本化（/api/v1/）
- [ ] SSE 流式响应无背压控制（`queue.Queue()` 无 maxsize）
- [ ] 前端未展示 RAG 引用来源（后端已发送 citations SSE 事件）
- [ ] AGENTS.md 需同步更新（当前已修复）
