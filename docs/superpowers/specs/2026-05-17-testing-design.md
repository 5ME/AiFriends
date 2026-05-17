# AI Friends — 测试体系设计

> 日期：2026-05-17
> 状态：待实施
> 目标：从零搭建 pytest 测试体系，覆盖 auth、friend、character、chat agent、memory agent

## 一、技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| 测试框架 | pytest + pytest-django | Python 社区标准，fixture 系统强大 |
| 数据工厂 | model_bakery | 一行创建模型实例，自动处理 ImageField |
| Mock 库 | pytest-mock (unittest.mock 封装) | LLM / WebSocket / LanceDB 全覆盖 |
| 数据库 | 阶段 1 用 SQLite，迁移后切 PostgreSQL 复跑 | Django ORM 屏蔽差异，迁移后不改测试代码 |

## 二、新增依赖

```
# requirements.txt 新增
pytest>=8.0
pytest-django>=4.0
pytest-mock>=3.0
model_bakery>=1.0
```

## 三、目录结构

```
backend/
├── pytest.ini                          # [pytest] DJANGO_SETTINGS_MODULE = backend.settings
├── web/
│   ├── tests/                          # 替代旧的 tests.py
│   │   ├── __init__.py
│   │   ├── conftest.py                 # 全局 fixtures
│   │   ├── test_auth.py                # 登录/注册/Token刷新/登出
│   │   ├── test_friend.py              # 好友创建/删除/列表/权限
│   │   ├── test_character.py           # 角色 CRUD + 权限 + 图片上传
│   │   ├── test_chat_agent.py          # LangGraph 图逻辑 + SSE 端点
│   │   └── test_memory_agent.py        # 记忆摘要触发逻辑
```

## 四、pytest.ini

```ini
[pytest]
DJANGO_SETTINGS_MODULE = backend.settings
python_files = tests/test_*.py
addopts = -v --tb=short
```

## 五、全局 Fixtures（web/tests/conftest.py）

| Fixture | 产出 | 用途 |
|---------|------|------|
| `api_client` | 未认证的 `APIClient()` | 公开端点测试 |
| `user` | `baker.make(User)` | 所有需认证的端点 |
| `auth_client` | APIClient + Bearer token + refresh cookie | 已认证请求 |
| `user_profile` | `baker.make(UserProfile, user=user)` | 角色/好友测试 |
| `character` | `baker.make(Character, author=user_profile)` | 好友测试 |
| `friend` | `baker.make(Friend, user_profile=user_profile, character=character)` | 消息测试 |

`db` 为 pytest-django 内置 fixture，标记数据库访问。

## 六、测试用例清单

### 6.1 test_auth.py（12 个用例）

| # | 测试 | 期望 |
|---|------|------|
| 1 | login_success | 200 + access_token + refresh cookie |
| 2 | login_wrong_password | 401 |
| 3 | login_empty_username | 400 |
| 4 | login_empty_password | 400 |
| 5 | register_success | 200 + User + UserProfile 均已创建 |
| 6 | register_duplicate_username | 409 |
| 7 | register_empty_fields | 400 |
| 8 | refresh_token_success | 200 + 新 access_token |
| 9 | refresh_token_missing | 401（cookie 不存在） |
| 10 | refresh_token_expired | 401 |
| 11 | logout_success | 200 + refresh cookie 已清除 |
| 12 | get_user_info | 200 + user_id, username, photo, profile |

### 6.2 test_friend.py（12 个用例）

| # | 测试 | 期望 |
|---|------|------|
| 1 | get_or_create_new | 200 + Friend 已创建 |
| 2 | get_or_create_duplicate | 200 + 返回已有 Friend（不重复） |
| 3 | get_or_create_missing_character | 400（character_id 缺失） |
| 4 | get_or_create_character_not_found | 404（角色不存在） |
| 5 | get_or_create_requires_auth | 401（无 token） |
| 6 | remove_success | 200 + Friend 已从 DB 删除 |
| 7 | remove_other_users_friend | 404（按 user_profile 过滤，查不到别人的） |
| 8 | get_list | 200 + 按 last_active 排序 + 分页 |
| 9 | is_friend_true | 200 + is_friend: true + friend_id 存在 |
| 10 | is_friend_false | 200 + is_friend: false + friend_id: null |
| 11 | get_count | 200 + friend_count 正确 |
| 12 | get_or_create_character_deleted | 404（角色已被删除） |

### 6.3 test_character.py（11 个用例）

| # | 测试 | 期望 |
|---|------|------|
| 1 | create_success | 200 + Character 已创建 |
| 2 | create_no_auth | 401 |
| 3 | create_empty_name | 400 |
| 4 | create_empty_profile | 400 |
| 5 | get_single_own | 200（自己的角色可见） |
| 6 | get_single_other_author | 未找到（按 author 过滤） |
| 7 | update_success | 200 + 字段更新 |
| 8 | update_not_author | 按 author 过滤，非作者未找到 |
| 9 | delete_success | 200 + Character 已从 DB 删除 |
| 10 | delete_not_author | 按 author 过滤，非作者未找到 |
| 11 | get_list | 200 + 分页正确 + characters 数组 |

### 6.4 test_chat_agent.py（深度测试）

**层级 1：LangGraph 图逻辑（单元测试）**

| # | 测试 | 期望 |
|---|------|------|
| 1 | agent_no_tool_calls | LLM 返回纯文本 AIMessage → 直接 END |
| 2 | agent_with_tool_calls | LLM 返回 tool_calls → 路由到 tools 节点 |
| 3 | tools_to_agent_loop | tools 节点执行 → 返回到 agent |
| 4 | get_time_tool | 返回当前时间的格式化字符串 |
| 5 | search_knowledge_base_tool | Mock LanceDB → 返回 chunks |

Mock 策略：
- `patch` 掉 `ChatGraph` 中的 `ChatOpenAI`，替换 `invoke()` 返回预设 AIMessage
- `patch` 掉 `lancedb.connect`，返回 mock table

**层级 2：SSE 端点（集成测试）**

| # | 测试 | 期望 |
|---|------|------|
| 6 | sse_text_stream | data 行格式 `{"content": "..."}` |
| 7 | sse_done_marker | 最后一条为 `[DONE]` |
| 8 | sse_message_created | 流结束后 Message 记录已写入 DB |
| 9 | sse_friend_not_found | 好友不存在 → 错误流 |
| 10 | sse_requires_auth | 无 token → 401 |

Mock 策略：
- `patch` 掉 `ChatGraph.create_app()` 返回 mock compiled graph，其 `astream` 产生预设 chunk 序列
- `patch` 掉 `websockets.connect` 避免真实 TTS 连接
- 使用 `auth_client.post()` + 迭代 `StreamingHttpResponse.streaming_content`

### 6.5 test_memory_agent.py（4 个用例）

| # | 测试 | 期望 |
|---|------|------|
| 1 | memory_triggered_at_10 | 第 10 条消息后 `update_memory` 被调用 |
| 2 | memory_not_triggered_at_5 | 第 5 条消息后不触发 |
| 3 | memory_field_updated | `Friend.memory` 被写入新值 |
| 4 | memory_agent_graph | Mock LLM → 图返回摘要 AIMessage |

Mock 策略：
- `patch` 掉 `MemoryGraph` 中的 `ChatOpenAI`，`invoke()` 返回包含摘要的 AIMessage

## 七、Chat Agent Mock 架构（关键设计）

```
test_chat_agent.py
    │
    ├── 层级 1：LangGraph 图逻辑
    │   @pytest.fixture → mock_chat_openai
    │   替换 ChatOpenAI.invoke()
    │   测试 graph 的节点和边路由
    │
    ├── 层级 2：SSE 端点集成
    │   @pytest.fixture → mock_chat_graph
    │   替换 ChatGraph.create_app() 返回 mock compiled graph
    │   mock.astream() → yield 预设 chunk 序列
    │   测试 SSE 格式 + Message 持久化
    │
    └── 层级 3：Memory Agent
        @pytest.fixture → mock_memory_llm
        替换 memory graph 中的 ChatOpenAI
        验证 Friend.memory 字段写入
```

### Mock 链说明

测试 SSE 端点时需要 mock 整条链路：
1. `ChatGraph.create_app()` → 返回 mock graph
2. mock graph 的 `astream()` → 产生 chunk 序列（含 content + usage_metadata）
3. `websockets.connect` → 返回 mock ws（避免真实 TTS WebSocket）
4. `threading.Thread` → 可选 patch 为同步执行（简化测试）

## 八、执行顺序与工时

```
第 1 步（0.5 天）：pip install + pytest.ini + conftest.py
第 2 步（1 天）  ：test_auth.py
第 3 步（1 天）  ：test_friend.py
第 4 步（1 天）  ：test_character.py
第 5 步（2 天）  ：test_chat_agent.py + test_memory_agent.py
```

每步结束 `pytest` 全绿。

## 九、数据库迁移策略

- **阶段 1**：测试全跑在 SQLite 上（Django TestCase 自动创建 test_ 库）
- **阶段 2（PostgreSQL 迁移后）**：`settings.py` 中 `DATABASES` 切到 PostgreSQL，`pytest` 全量重跑
- 如果全绿 → 迁移成功；如果有失败 → 测试暴露了 SQLite 宽松约束下隐藏的 bug

## 十、验证方式

```bash
cd backend
pytest                              # 全量
pytest web/tests/test_auth.py       # 单模块
pytest -k "test_login"              # 按关键字
pytest --tb=long                    # 失败时完整 traceback
```

## 十一、不在范围内

- 覆盖率报告（pytest-cov）：等所有测试写完后再引入
- CI/CD（GitHub Actions）：等测试稳定后
- ASR 端点测试：涉及 DashScope WebSocket，调试成本高，后续补充
- 前端测试（Vitest）：当前阶段只做后端
