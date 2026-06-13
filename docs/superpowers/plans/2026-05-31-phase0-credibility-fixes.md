# Phase 0: 可信度修复 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修掉两份 Review 报告标记的"面试官第一眼"扣分项，让项目 README/配置/数据模型三者一致。

**Architecture:** 7 个独立任务，无相互依赖，可任意顺序执行。改动范围：文档（README）、配置（docker-compose/settings）、Bug 修复（Memory Agent/JSONField）、代码清理（LanceDB/Photo.vue）。

**Tech Stack:** Django 6.0, PostgreSQL 17, Docker Compose, Vue 3

---

## 文件影响总览

| 操作 | 文件 |
|------|------|
| 修改 | `README.md` |
| 修改 | `docker-compose.yml` |
| 修改 | `backend/backend/settings.py` |
| 修改 | `backend/web/views/friend/message/memory/tasks.py` |
| 修改 | `backend/web/views/friend/message/chat/graph.py` |
| 修改 | `backend/web/views/friend/message/chat/chat.py` |
| 新增 | `backend/web/migrations/0015_fix_message_input_jsonfield.py` |
| 新增 | `frontend/src/composables/useImageCropper.js` |
| 修改 | `frontend/src/views/user/profile/components/Photo.vue` |
| 修改 | `frontend/src/views/create/character/components/Photo.vue` |

---

### Task 1: README 全面更新

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`（如有过期内容）

- [ ] **Step 1: 更新测试数量（2 处）**

第 25 行：
```markdown
- pytest 自动化测试覆盖核心链路（99 个测试）
```

第 51 行：
```bash
python -m pytest web/tests/ -v   # 99 个测试
```

- [ ] **Step 2: 更新"已知限制"章节（第 157-165 行）**

替换整节为：
```markdown
## 已知限制

- [ ] 音色仅支持系统内置，暂不支持用户自定义
- [ ] 未做压测，暂无容量评估数据
- [ ] 无 API 版本化（/api/v1/）
- [ ] 无速率限制和成本治理
```

> 移除项及其原因：
> - ~~知识库全局预置~~ → 已支持用户上传文档构建个人 RAG
> - ~~Memory Agent 同步执行~~ → 已迁移到 Celery + Redis 异步任务
> - ~~未做 Docker 容器化~~ → 已有 docker-compose.yml（PG + Redis）
> - ~~测试使用 PostgreSQL 独立测试库~~ → 已是当前状态，非"限制"

- [ ] **Step 3: 在"功能"章节增加新功能描述**

在第 20-25 行之间插入：
```markdown
- 用户文档 RAG 知识库：上传 txt/md/pdf → 异步解析/分块/embedding → pgvector 检索
- Celery + Redis 异步任务队列（Memory Agent 摘要 + 文档处理）
- 健康检查端点（GET /api/health/）+ Request ID 全链路追踪
```

- [ ] **Step 4: 更新"快速开始"增加 Celery 和 Docker 说明**

在第 45 行 `python manage.py runserver` 之后插入：
```markdown
### 基础设施（Docker Compose）

```bash
wsl docker compose up -d   # 启动 PostgreSQL 17 + pgvector + Redis 7
```

### Celery Worker

```bash
cd backend
celery -A backend worker --loglevel=info --pool=solo
```

> Memory Agent 摘要和文档处理通过 Celery 异步执行，需同时运行 Django 和 Celery Worker。
```

- [ ] **Step 5: 增加架构图（ASCII/Mermaid）**

在"项目结构"之前插入：
```markdown
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
```

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: sync README with current state — 99 tests, Celery async, user RAG, Docker Compose"
```

---

### Task 2: docker-compose 可移植

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: 修改 PostgreSQL 密码为环境变量**

将第 6 行：
```yaml
      POSTGRES_PASSWORD: Kakarot001#
```
改为：
```yaml
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-changeme}
```

- [ ] **Step 2: 修改 volumes 为 named volumes**

将第 9-11 行：
```yaml
    volumes:
      - /home/ygq/postgres-data:/var/lib/postgresql/data
      - /home/ygq/ai-friends/init.sql:/docker-entrypoint-initdb.d/init.sql
```
改为：
```yaml
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
```

- [ ] **Step 3: 修改 Redis volume 为 named volume**

将第 19-20 行：
```yaml
    volumes:
      - /home/ygq/redis-data:/data
```
改为：
```yaml
    volumes:
      - redis-data:/data
```

- [ ] **Step 4: 在文件末尾声明 named volumes**

在最后一行 `restart: unless-stopped` 之后添加：
```yaml

volumes:
  postgres-data:
  redis-data:
```

- [ ] **Step 5: 验证 docker-compose 语法**

```bash
wsl docker compose config
```
Expected: 无错误输出，显示解析后的完整配置

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml
git commit -m "fix: make docker-compose portable — env-var passwords, named volumes, relative paths"
```

---

### Task 3: SECRET_KEY 去弱 fallback

**Files:**
- Modify: `backend/backend/settings.py:27-29`

- [ ] **Step 1: 修改 SECRET_KEY 读取逻辑**

当前代码（第 27 行）：
```python
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-change-me-in-production')
```

替换为：
```python
from django.core.exceptions import ImproperlyConfigured

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'django-insecure-dev-only-not-for-production'
    else:
        raise ImproperlyConfigured(
            'DJANGO_SECRET_KEY environment variable is required when DEBUG=False'
        )
```

> 注意：`ImproperlyConfigured` 的 import 应放在文件顶部已有 import 区域（第 1-18 行），与其他 django 导入放在一起。

- [ ] **Step 2: 在文件顶部添加 import**

在第 10 行附近（现有 `from django.core...` import 附近）：
```python
from django.core.exceptions import ImproperlyConfigured
```

如果 settings.py 使用的是 `from django.core.exceptions import ...` 中的已有导入，加到同一行。

先检查：`grep -n "from django" backend/backend/settings.py`
确认 import 位置后添加。

- [ ] **Step 3: 验证 — 无环境变量时启动应报错**

```bash
cd backend
set DJANGO_SECRET_KEY=
set DJANGO_DEBUG=false
python -c "import os; os.environ['DJANGO_DEBUG']='false'; exec(open('backend/settings.py').read())"
```

Expected: `ImproperlyConfigured: DJANGO_SECRET_KEY environment variable is required when DEBUG=False`

- [ ] **Step 4: 验证 — DEBUG 模式下无环境变量可启动**

```bash
cd backend
set DJANGO_SECRET_KEY=
set DJANGO_DEBUG=true
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 5: Commit**

```bash
git add backend/backend/settings.py
git commit -m "fix: reject startup without DJANGO_SECRET_KEY in production mode"
```

---

### Task 4: Memory Agent backlog bug 修复

**Files:**
- Modify: `backend/web/views/friend/message/memory/tasks.py`

**问题**：当消息积压超过 30 条时，`last_summarized_count` 被推进到全部消息数，导致中间消息永远不进入摘要。

**当前代码**（第 43 行获取 msg_count，第 54 行错误地使用 msg_count 作为 cursor）：
```python
msg_count = Message.objects.filter(friend=friend).count()  # line 43 — 保留不变
...
friend.last_summarized_count = msg_count  # line 54 — BUG: 设为 50，实际只摘要了 30 条
```

**修复**：只推进实际摘要的消息数。保留第 42-45 行不变（friend 对象和 msg_count 变量），仅修改第 46-55 行（app_graph 创建到 save）。

- [ ] **Step 1: 修改 update_memory_task 中 last_summarized_count 的更新逻辑**

将第 **46-55 行**区域（从 `app_graph = ...` 到 `friend.save()`）改为：

```python
        app_graph = MemoryGraph.create_app()
        inputs = {
            'messages': [create_system_message(), create_human_message(friend)]
        }
        res = app_graph.invoke(inputs)
        friend.memory = res['messages'][-1].content

        # 只推进本次实际摘要的消息数，防止积压超过 30 条时遗漏中间消息
        # 如果有剩余 backlog，下次触发时继续处理
        skip = friend.last_summarized_count
        take = min(msg_count - skip, 30)
        friend.last_summarized_count = skip + take
        friend.save()
```

> 关键：第 42-45 行（`friend = ...`, `msg_count = ...`, `logger.info(...)`）保留不变。`msg_count` 和 `friend` 变量在这些行中声明，后续代码依赖它们。

- [ ] **Step 2: 验证 — 运行现有 Memory 测试确保不回归**

```bash
cd backend
python -m pytest web/tests/test_memory_agent.py -v
```

Expected: 6 passed（TestMemoryTrigger, TestMemoryField, TestMemoryFailureCompensation, TestMemoryGraph）

- [ ] **Step 3: 手动验证逻辑正确性**

Scenario: `msg_count=50`, `last_summarized_count=0`
- `take = min(50-0, 30) = 30`
- `last_summarized_count = 0 + 30 = 30` ✅

Scenario: `msg_count=60`, `last_summarized_count=30`（上次处理了前 30 条）
- `take = min(60-30, 30) = 30`
- `last_summarized_count = 30 + 30 = 60` ✅

Scenario: `msg_count=55`, `last_summarized_count=50`
- `take = min(55-50, 30) = 5`
- `last_summarized_count = 50 + 5 = 55` ✅

- [ ] **Step 4: Commit**

```bash
git add backend/web/views/friend/message/memory/tasks.py
git commit -m "fix: prevent memory summary data loss when backlog exceeds 30 messages
\    
\    last_summarized_count now advances by actual summarized count (skip + take)
\    instead of total message count, preventing message gaps when the Memory
\    Agent hasn't run for many turns.
\    
\    Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: 清理 LanceDB 旧引用

**Files:**
- Modify: `backend/web/views/friend/message/chat/graph.py:30`
- Modify: `AGENTS.md:11,94,109`
- Modify: `requirements.txt:40`

**影响范围**：当前 `git grep -i lancedb` 返回 4 个位置：
- `graph.py:30` — 注释中 `（LanceDB）`
- `AGENTS.md:11` — `LanceDB for vector storage`
- `AGENTS.md:94` — `LanceDB vector search over Bailian docs`
- `AGENTS.md:109` — `LanceDB vector storage and a custom embeddings wrapper`
- `requirements.txt:40` — `lancedb==0.30.2`（已不再使用但未删除）

- [ ] **Step 1: 修改 graph.py 注释**

第 30 行，将：
```python
        # Tool 2: 知识库向量检索（LanceDB）
```
改为：
```python
        # Tool 2: 知识库向量检索（pgvector）
```

- [ ] **Step 2: 修改 AGENTS.md 三处 LanceDB 描述**

第 11 行：`LanceDB for vector storage` → `pgvector for vector storage`

第 94 行：`LanceDB vector search over Bailian docs` → `pgvector vector search over Bailian docs`

第 109 行：`LanceDB vector storage and a custom embeddings wrapper` → `pgvector vector storage and a custom embeddings wrapper`

- [ ] **Step 3: 删除 requirements.txt 中的 LanceDB 依赖**

删除第 40 行（或包含 `lancedb==0.30.2` 的行）。

- [ ] **Step 4: 全仓搜索确认无残留**

```bash
git grep -i lancedb
```

Expected: No results

- [ ] **Step 5: Commit**

```bash
git add backend/web/views/friend/message/chat/graph.py AGENTS.md requirements.txt
git commit -m "chore: remove LanceDB references and dependency, replaced by pgvector"
```

---

### Task 6: Message.input JSONField 修复

**Files:**
- Modify: `backend/web/views/friend/message/chat/chat.py:188-191`
- Create: `backend/web/migrations/0015_fix_message_input_jsonfield.py`（自动生成 + 手动补充）

**背景**：模型定义 `input = models.JSONField(default=dict)`，但迁移 0006 将其改为了 `TextField`——数据库 schema 和模型定义已不同步。修复需要两步：(1) 停止写入 `json.dumps()` 字符串；(2) 将字段从 TextField 改回 JSONField 并转换已有数据。

- [ ] **Step 1: 修改 chat.py 中的 Message 保存逻辑**

第 185-196 行，将：
```python
            Message.objects.create(
                friend=friend,
                user_message=message[:5000],
                input=json.dumps(
                    [m.model_dump() for m in inputs['messages']],
                    ensure_ascii=False
                )[:50000],
                output=''.join(full_output)[:5000],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            )
```

改为：
```python
            Message.objects.create(
                friend=friend,
                user_message=message[:5000],
                input=[m.model_dump() for m in inputs['messages']],
                output=''.join(full_output)[:5000],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            )
```

> JSONField 自动序列化 Python list/dict → PostgreSQL jsonb。不再需要 `json.dumps()`。
> 移除 `[:50000]` 字符截断——对原生 list 无效（会报 TypeError，因为 list 不支持 slice 到字符）。`max_length=50000` 已限制 jsonb 列大小，正常 ~20 条消息的 model_dump 远小于此值。

- [ ] **Step 2: 确认 json 模块不再需要（如果仅用于此处）**

检查 `chat.py` 中是否还有其他 `json.dumps` 调用：
```bash
grep -n "json\." backend/web/views/friend/message/chat/chat.py
```

如果还有 TTS/SSE 中使用 `json.dumps`，保留 `import json`。确认第 144/171/174/176/234/278/293 行仍有使用，`import json` 不应删除。

- [ ] **Step 3: 生成 schema 迁移（TextField → JSONField）**

```bash
cd backend
python manage.py makemigrations --name fix_message_input_jsonfield
```

Django 会检测到模型 `JSONField` 与数据库 `TextField` 不一致，自动生成 `0015_fix_message_input_jsonfield.py`，包含 `AlterField` 操作。

- [ ] **Step 4: 补充数据迁移**

在自动生成的 `0015_fix_message_input_jsonfield.py` 中，在 `AlterField` **之前**插入数据转换步骤：

```python
from django.db import migrations, models
from json import loads, JSONDecodeError


def convert_input_to_json(apps, schema_editor):
    """将 Message.input 中存为 JSON 字符串的数据转为原生 Python 对象"""
    Message = apps.get_model('web', 'Message')
    for msg in Message.objects.exclude(input__isnull=True).exclude(input={}):
        if isinstance(msg.input, str):
            try:
                msg.input = loads(msg.input)
                msg.save(update_fields=['input'])
            except (JSONDecodeError, TypeError):
                # 无法解析的字符串设为空对象
                msg.input = {}
                msg.save(update_fields=['input'])


def reverse_convert(apps, schema_editor):
    pass  # 不回退已有数据的转换


class Migration(migrations.Migration):
    dependencies = [
        ('web', '0014_add_last_summarized_count'),
    ]

    operations = [
        # Step A: 先将字符串数据转为原生 JSON（此时仍是 TextField 但存的是 dict）
        migrations.RunPython(convert_input_to_json, reverse_convert),
        # Step B: Django 自动生成的 AlterField（TextField → JSONField）
        # Django 会在 makemigrations 时自动生成此操作
    ]
```

> 核心逻辑：`isinstance(msg.input, str)` 检测是否为旧的 `json.dumps()` 字符串，`loads()` 转回原生 dict。Django 自动生成的 `AlterField` 会将字段类型从 TextField 改为 JSONField。

- [ ] **Step 5: 运行迁移**

```bash
cd backend
python manage.py migrate
```

Expected: `Applying web.0015_fix_message_input_jsonfield... OK`

- [ ] **Step 6: 运行测试验证**

```bash
cd backend
python -m pytest web/tests/test_chat_agent.py -v
```

Expected: 5 passed

- [ ] **Step 7: Commit**

```bash
git add backend/web/views/friend/message/chat/chat.py backend/web/migrations/0015_fix_message_input_jsonfield.py
git commit -m "fix: store native list in Message.input JSONField instead of json.dumps string

    Model defines JSONField(default=dict) but migration 0006 changed it to
    TextField. This commit:
    1. Removes json.dumps() in chat.py — stores list directly
    2. Migration 0015: converts existing string data → native JSON,
       then AlterField TextField → JSONField (model-declared type).
    
    Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Photo.vue 去重

**Files:**
- Create: `frontend/src/composables/useImageCropper.js`
- Modify: `frontend/src/views/user/profile/components/Photo.vue`
- Modify: `frontend/src/views/create/character/components/Photo.vue`

两个 Photo.vue 的 Croppie 图片裁剪逻辑 90% 相同，差异仅在于 viewport 尺寸和 modal 按钮样式。实际代码模式：
- `import Croppie from "croppie"` — 顶层静态导入
- `let croppie = null` — 普通变量，非 ref
- 输入：`FileReader.readAsDataURL()` → base64 data URL
- 输出：`croppie.result({type: 'base64', size: 'viewport'})` → base64 字符串
- Modal：原生 `<dialog>` showModal()/close()，非 v-if ref

- [ ] **Step 1: 创建共享 composable**

创建 `frontend/src/composables/useImageCropper.js`：

```javascript
import Croppie from 'croppie'
import 'croppie/croppie.css'
import { nextTick } from 'vue'

/**
 * 共享的 Croppie 图片裁剪逻辑 — 与现有 Photo.vue 行为完全一致。
 * 输入 base64 data URL，输出 base64 字符串。
 *
 * @param {Object} options
 * @param {number} options.viewportWidth
 * @param {number} options.viewportHeight
 * @param {string} options.viewportType - 'square' | 'circle'
 * @param {number} options.boundaryWidth
 * @param {number} options.boundaryHeight
 */
export function useImageCropper(options = {}) {
  const {
    viewportWidth = 200,
    viewportHeight = 200,
    viewportType = 'square',
    boundaryWidth = 300,
    boundaryHeight = 300,
  } = options

  let croppie = null

  function init(el, photoUrl) {
    if (!croppie) {
      croppie = new Croppie(el, {
        viewport: { width: viewportWidth, height: viewportHeight, type: viewportType },
        boundary: { width: boundaryWidth, height: boundaryHeight },
        enableOrientation: true,
        enforceBoundary: true,
      })
    }
    croppie.bind({ url: photoUrl })
  }

  async function crop() {
    if (!croppie) return null
    return croppie.result({ type: 'base64', size: 'viewport' })
  }

  function destroy() {
    croppie?.destroy()
    croppie = null
  }

  return { init, crop, destroy }
}
```

> API 设计理由：
> - **顶层导入 Croppie**：与原代码一致的静态 import，避免动态 `await import()` 引入额外异步复杂度。
> - **输入 base64 / 输出 base64**：与原代码 `reader.result` → `croppie.result({type:'base64'})` 完全一致，调用方 `<img :src="myPhoto">` 可直接使用返回值，无需 `URL.createObjectURL()`。
> - **`init(el, photoUrl)`**：由调用方负责打开 modal 和传入 DOM 元素引用，composable 只管理 Croppie 实例生命周期。
> - **`destroy()` 暴露给 `onBeforeUnmount`**：调用方在组件卸载时清理。

- [ ] **Step 2: 改造 profile/Photo.vue**

移除原有的 Croppie 导入和变量声明（`import Croppie from "croppie"`, `import 'croppie/croppie.css'`, `let croppie = null`），替换为 composable：

```javascript
import { useImageCropper } from '@/composables/useImageCropper.js'

const { init: initCroppie, crop: doCrop, destroy: destroyCroppie } = useImageCropper({
  viewportWidth: 200,
  viewportHeight: 200,
  viewportType: 'square',
  boundaryWidth: 300,
  boundaryHeight: 300,
})
```

修改 `openModal` 函数，去掉 Croppie 初始化代码：
```javascript
async function openModal(photo) {
  modalRef.value.showModal()
  await nextTick()
  initCroppie(croppieRef.value, photo)
}
```

修改 `crop` 函数：
```javascript
async function crop() {
  const result = await doCrop()
  if (result) {
    myPhoto.value = result
  }
  modalRef.value.close()
}
```

修改 `onBeforeUnmount`：
```javascript
onBeforeUnmount(() => {
  destroyCroppie()
})
```

> 删除：`import Croppie from "croppie"`, `import 'croppie/croppie.css'`, `let croppie = null`, 以及 `openModal` 中 `new Croppie(...)` 和 `croppie.bind(...)` 的原始代码。

- [ ] **Step 3: 改造 create/character/Photo.vue**

读取 `frontend/src/views/create/character/components/Photo.vue`，确认其 Croppie 参数后，用相同的 composable 替换。参数可能不同（如 viewport 更大），以实际文件中的值为准。

典型替换（参数以实际文件为准）：
```javascript
import { useImageCropper } from '@/composables/useImageCropper.js'

const { init: initCroppie, crop: doCrop, destroy: destroyCroppie } = useImageCropper({
  viewportWidth: 200,
  viewportHeight: 200,
  viewportType: 'circle',  // 角色头像用圆形
  boundaryWidth: 300,
  boundaryHeight: 300,
})
```

其余步骤与 Step 2 相同：替换 `openModal`、`crop` 函数、`onBeforeUnmount` 中的 Croppie 逻辑。

- [ ] **Step 4: 确认两个 Photo.vue 功能正常**

前端启动后验证：
1. Profile 页面 → 点击头像 → 裁剪弹窗正常 → 裁剪后头像更新
2. 创建角色页面 → 上传照片 → 裁剪弹窗正常 → 裁剪后预览正常

- [ ] **Step 5: 运行现有前端构建确认无编译错误**

```bash
cd frontend
npm run build
```

Expected: Build succeeds without errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/composables/useImageCropper.js frontend/src/views/user/profile/components/Photo.vue frontend/src/views/create/character/components/Photo.vue
git commit -m "refactor: extract Croppie image cropper into shared useImageCropper composable

    Two Photo.vue components (profile avatar + character creation) had ~90%
    duplicated Croppie logic. Extracted into a single composable with
    configurable viewport/boundary/shape parameters.
    
    Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## 完成检查清单

- [ ] `git grep -i lancedb` 无结果（含 AGENTS.md、graph.py、requirements.txt）
- [ ] `python -m pytest web/tests/ -v` — 99 passed
- [ ] `wsl docker compose config` — 无语法错误
- [ ] `grep -c "51 个测试" README.md` — 0
- [ ] `grep -c "同步执行" README.md` — 0
- [ ] `grep -c "全局预置" README.md` — 0
- [ ] `grep -c "未做 Docker" README.md` — 0
- [ ] Memory Agent 测试全部通过（6 passed）
- [ ] `python manage.py migrate` — migration 0015 applied
- [ ] `npm run build` 前端构建成功
- [ ] Profile 页面头像裁剪功能正常
- [ ] 创建角色页面头像裁剪功能正常
