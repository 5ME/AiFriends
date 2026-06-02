# AI Friends

AI 虚拟角色聊天平台 — 用户可创建 AI 角色并与之进行文字 + 语音聊天，支持长期记忆和 RAG 知识库检索。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Django 6.0 + Django REST Framework + JWT (PostgreSQL 17 + pgvector 0.8) |
| 前端 | Vue 3 (Composition API) + Vite 7 + Pinia + Vue Router 5 |
| UI | Tailwind CSS 4 + daisyUI 5 |
| AI | 阿里云 DashScope（通义千问 / DeepSeek-V3.2） + LangChain/LangGraph |
| 语音 | DashScope TTS (WebSocket) + ASR (WebSocket) + 浏览器端 VAD (Silero VAD / ONNX) |
| 向量存储 | pgvector (1024 维 DashScope text-embedding-v4) |
| 部署 | Gunicorn + Nginx (Ubuntu) |

## 功能

- 创建 / 编辑 / 删除自定义 AI 虚拟角色
- 文字 + 语音双模态聊天，AI 回复支持文字 + 语音同步流式输出
- 聊天上下文长期记忆，每 10 条消息触发 Memory Agent 自动摘要
- RAG 知识库检索（pgvector 余弦距离搜索）
- 用户注册登录（JWT access/refresh 双令牌认证，httpOnly cookie）
- 首页角色探索 + 好友关系管理
- pytest 自动化测试覆盖核心链路（99 个测试）
- 用户文档 RAG 知识库：上传 txt/md/pdf → 异步解析/分块/embedding → pgvector 检索
- Celery + Redis 异步任务队列（Memory Agent 摘要 + 文档处理）
- 健康检查端点（GET /api/health/）+ Request ID 全链路追踪

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
| `npm run build` | cloud（生产） | `https://115.190.245.146` |
| `$env:VITE_PLATFORM='django'; npm run build` | django（本地打包） | `http://127.0.0.1:8000` |

---

## 部署

### 手动部署（云服务器）

```bash
cd frontend && npm run build        # 自动使用 cloud 模式
cd backend
python manage.py collectstatic
gunicorn --workers 3 --bind unix:gunicorn.sock backend.wsgi:application
celery -A backend worker --loglevel=info --pool=solo
# Nginx 反向代理配置详见 服务器部署.md
```

> 生产部署前请确保 `.env` 中 `DJANGO_SECRET_KEY` 已设置且 `DJANGO_DEBUG=false`。

---

## 运行测试

```bash
cd backend
python -m pytest web/tests/ -v   # 99 个测试
```

## 架构

```
┌─────────────┐     SSE/HTTP      ┌──────────────────────────────────┐
│   Vue 3     │ ◄──────────────► │  Django + DRF (Gunicorn)         │
│   Vite 7    │                   │  ├─ Chat Agent (LangGraph)       │
│   daisyUI 5 │                   │  ├─ Memory Agent (LangGraph)     │
└─────────────┘                   │  ├─ RAG (pgvector)              │
                                  │  └─ JWT Auth                    │
                                  └──────────┬───────────────────────┘
                                             │
                   ┌─────────────────────────┼─────────────────────────┐
                   │                         │                         │
            ┌──────▼──────┐          ┌──────▼──────┐          ┌──────▼──────┐
            │ PostgreSQL  │          │ Redis 7     │          │ DashScope   │
            │ + pgvector  │          │ (Broker)    │          │ LLM/TTS/ASR │
            └─────────────┘          └──────┬──────┘          │ + Embedding │
                                            │                 └─────────────┘
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
│   │   ├── settings.py                   # 项目设置（DB、JWT、CORS 等）
│   │   ├── urls.py                       # 根 URL 配置
│   │   ├── wsgi.py                       # WSGI 入口（Gunicorn）
│   │   └── asgi.py                       # ASGI 入口
│   │
│   ├── web/                              # 主 Django 应用
│   │   ├── models/                       # 数据模型
│   │   │   ├── user.py                   #   UserProfile
│   │   │   ├── character.py              #   Character、Voice
│   │   │   ├── friend.py                 #   Friend、Message、SystemPrompt
│   │   │   └── document.py               #   UserDocument、DocumentChunk (pgvector)
│   │   │
│   │   ├── views/                        # API 视图（文件即视图，无序列化器）
│   │   │   ├── index.py                  #   前端 SPA 入口视图
│   │   │   ├── health.py                 #   健康检查端点
│   │   │   ├── user/account/             #   登录、注册、登出、刷新令牌、获取用户信息
│   │   │   ├── user/profile/             #   个人资料更新
│   │   │   ├── create/character/         #   角色 CRUD + 音色列表
│   │   │   │   └── voice/custom/         #   自定义音色（阿里云 API）
│   │   │   ├── homepage/                 #   首页角色列表
│   │   │   ├── friend/                   #   好友关系管理 + is_friend 检查
│   │   │   │   └── message/
│   │   │   │       ├── chat/             #   LangGraph 聊天 agent + SSE 流式
│   │   │   │       ├── asr/              #   语音识别（DashScope WS）
│   │   │   │       └── memory/           #   LangGraph 记忆摘要 agent (Celery)
│   │   │   ├── document/                 #   文档上传/列表/删除 + Celery 异步处理
│   │   │   └── utils/                    #   图片清理等工具
│   │   │
│   │   ├── middleware/                   # 中间件
│   │   │   └── request_id.py            #   Request ID + 请求耗时日志
│   │   │
│   │   ├── documents/                    # RAG 知识库
│   │   │   ├── loaders/                  #   文档加载器（txt/md/pdf）
│   │   │   └── services/                 #   embedding + chunker
│   │   │
│   │   ├── tasks.py                      # Celery autodiscover 入口
│   │   │
│   │   ├── templates/                    # Django 模板
│   │   │   └── index.html                #   SPA 入口（开发时渲染 Vite 构建产物）
│   │   │
│   │   ├── urls.py                       # 应用 URL 路由 + SPA 兜底路由
│   │   ├── admin.py                      # Django Admin 注册
│   │   └── apps.py                       # AppConfig
│   │
│   ├── static/frontend/                  # Vite 构建输出（生产）
│   ├── media/                            # 用户上传文件（头像、角色背景等）
│   └── manage.py                         # Django CLI 入口
│
├── frontend/                             # Vue 3 SPA 前端
│   ├── src/
│   │   ├── main.js                       # Vue 应用入口
│   │   ├── App.vue                       # 根组件（用户信息拉取 + RouterView）
│   │   │
│   │   ├── views/                        # 页面视图
│   │   │   ├── homepage/                 #   首页（角色卡片网格 + 无限滚动）
│   │   │   ├── friend/                   #   好友列表页
│   │   │   ├── create/                   #   创作页 + 编辑角色
│   │   │   ├── user/account/             #   登录、注册
│   │   │   ├── user/profile/             #   编辑个人资料
│   │   │   ├── user/space/               #   用户空间
│   │   │   └── error/                    #   404 页面
│   │   │
│   │   ├── components/                   # 可复用组件
│   │   │   ├── navbar/                   #   顶部导航栏 + 侧边抽屉 + 用户菜单
│   │   │   └── character/                #   角色卡片 + 详情弹窗
│   │   │       └── chat_field/           #     聊天模态框（历史、输入、TTS 播放）
│   │   │
│   │   ├── router/index.js               # Vue Router（路由表 + 登录守卫）
│   │   ├── stores/user.js                # Pinia 用户状态 + JWT 令牌
│   │   ├── composables/                  # 可复用逻辑
│   │   │   ├── useImageCropper.js        #   Croppie 图片裁剪
│   │   │   └── useDocumentPolling.js     #   文档处理状态轮询
│   │   └── js/                           # 工具模块
│   │       ├── config/config.js          #   环境自动切换（vue/django/cloud）
│   │       ├── http/api.js               #   Axios 封装 + JWT 自动刷新
│   │       └── http/streamApi.js         #   SSE 流式客户端（AI 聊天）
│   │
│   ├── components/knowledge/             # 知识库组件
│   │   ├── UploadZone.vue                #   拖拽上传
│   │   └── DocumentCard.vue              #   文档卡片
│   ├── views/KnowledgeBase.vue           # 知识库页面
│   ├── public/favicon.ico
│   ├── index.html                        # HTML 入口
│   ├── vite.config.js                    # Vite 构建配置
│   └── package.json                      # Node 依赖 + 脚本
│
├── .github/workflows/test.yml            # GitHub Actions CI
├── AGENTS.md                             # Codex agent 指令
└── CLAUDE.md                             # Claude Code 项目指南
```

## 已知限制

- [ ] 音色仅支持系统内置，暂不支持用户自定义
- [ ] 未做压测，暂无容量评估数据
- [ ] 无 API 版本化（/api/v1/）
- [ ] 无速率限制和成本治理
