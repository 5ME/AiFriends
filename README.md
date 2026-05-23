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
- pytest 自动化测试覆盖核心链路（51 个测试）

## 快速开始

### 后端

```bash
cd backend
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API_KEY 等必填项

# 2. 安装依赖
pip install -r requirements.txt

# 3. 数据库迁移
python manage.py migrate

# 4. 启动开发服务器
python manage.py runserver        # http://127.0.0.1:8000
```

### 运行测试

```bash
cd backend
python -m pytest web/tests/ -v   # 51 个测试
```

### 前端

```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

> 开发时前端默认以 `vue` 模式运行，API 请求指向 `http://127.0.0.1:8000`。  
> 环境模式在 `frontend/src/js/config/config.js` 中切换：`vue`（纯前端开发）、`django`（后端开发）、`cloud`（生产）。

### 生产部署

1. 设置 `platform = 'cloud'` → `frontend/src/js/config/config.js`
2. `cd frontend && npm run build` → 构建产物输出到 `backend/static/frontend/`
3. `cd backend && python manage.py collectstatic`
4. 启动 Gunicorn：`gunicorn --workers 3 --bind unix:gunicorn.sock backend.wsgi:application`
5. Nginx 反向代理到 Gunicorn socket（详见 `服务器部署.md`）

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
│   │   │   └── friend.py                 #   Friend、Message、SystemPrompt
│   │   │   └── document.py               #   DocumentChunk (pgvector 向量字段)
│   │   │
│   │   ├── views/                        # API 视图（文件即视图，无序列化器）
│   │   │   ├── index.py                  #   前端 SPA 入口视图
│   │   │   ├── user/account/             #   登录、注册、登出、刷新令牌、获取用户信息
│   │   │   ├── user/profile/             #   个人资料更新
│   │   │   ├── create/character/         #   角色 CRUD + 音色列表
│   │   │   │   └── voice/                #   阿里云音色自定义（预留）
│   │   │   ├── homepage/                 #   首页角色列表
│   │   │   ├── friend/                   #   好友关系管理 + is_friend 检查
│   │   │   │   └── message/
│   │   │   │       ├── chat/             #   LangGraph 聊天 agent + SSE 流式
│   │   │   │       ├── asr/              #   语音识别（DashScope WS）
│   │   │   │       └── memory/           #   LangGraph 记忆摘要 agent
│   │   │   └── utils/                    #   图片清理等工具
│   │   │
│   │   ├── documents/                    # RAG 知识库
│   │   │   └── utils/                    #   自定义嵌入、文档插入、分块测试
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
│   ├── manage.py                         # Django CLI 入口
│   └── requirements.txt                  # Python 依赖
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
│   │   └── js/                           # 工具模块
│   │       ├── config/config.js          #   环境常量（vue/django/cloud 三模式）
│   │       ├── http/api.js               #   Axios 封装 + JWT 自动刷新
│   │       └── http/streamApi.js         #   SSE 流式客户端（AI 聊天）
│   │
│   ├── public/
│   │   └── favicon.ico
│   ├── index.html                        # HTML 入口
│   ├── vite.config.js                    # Vite 构建配置
│   └── package.json                      # Node 依赖 + 脚本
│
├── AGENTS.md                             # Codex agent 指令
└── CLAUDE.md                             # Claude Code 项目指南
```

## 已知限制

- [ ] 知识库目前为全局预置，暂不支持用户自行上传文档构建个人 RAG
- [ ] 音色仅支持系统内置，暂不支持用户自定义
- [ ] Memory Agent 当前在聊天请求线程内同步执行，大模型调用期间会占用 worker 资源
- [ ] 未做 Docker 容器化，部署需手动配置环境
- [ ] 未做压测，暂无容量评估数据
- [ ] 测试环境使用 SQLite，pgvector 查询仅在 PostgreSQL 运行环境中验证
