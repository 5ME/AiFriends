# AI Friends

AI 虚拟角色聊天平台 — 用户可创建 AI 角色并与之进行文字 + 语音聊天，支持长期记忆和 RAG 知识库检索。

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
