# AI Friends — PostgreSQL 迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SQLite → PostgreSQL 17.10 + pgvector 0.8.2，同步完成模型优化、向量库切换、profile 拆分

**Architecture:** 先改模型 → 改代码适配模型变更 → 切数据库 → migrate → 验证。pgvector 代码在模型迁移后写入，前端在 profile 拆分后适配。

**Tech Stack:** Django 6.0, psycopg2-binary, django-pgvector, Vue 3, conda py312

**Spec:** `docs/superpowers/specs/2026-05-17-postgresql-migration-design.md`

---

### Task 1: 新开分支 + 安装依赖

- [ ] **Step 1: 创建分支**

```bash
cd D:/MyProjects/AiFriends && git checkout -b feature/gqyin/postgresql-migration
```

- [ ] **Step 2: 安装 PostgreSQL 依赖**

```bash
conda run -n py312 pip install psycopg2-binary django-pgvector
```

- [ ] **Step 3: 写入 requirements.txt**

修改 `D:\MyProjects\AiFriends\requirements.txt`，末尾追加：

```
psycopg2-binary>=2.9
django-pgvector>=0.1
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add psycopg2-binary and django-pgvector dependencies"
```

---

### Task 2: 模型变更

**Files:**
- Modify: `backend/web/models/character.py`
- Modify: `backend/web/models/friend.py`
- Create: `backend/web/models/document.py`

- [ ] **Step 1: 修改 character.py — Voice 加 updated_at**

```python
# Voice 模型，改 created_at + 加 updated_at
class Voice(models.Model):
    name = models.CharField(max_length=100)
    voice_id = models.CharField(max_length=100, help_text="阿里云音色ID")
    profile = models.TextField(max_length=500, default='')
    is_builtin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)    # default=now → auto_now_add
    updated_at = models.DateTimeField(auto_now=True)         # 新增
```

- [ ] **Step 2: 修改 character.py — Character profile 拆分 + 索引**

```python
class Character(models.Model):
    author = models.ForeignKey(UserProfile, on_delete=models.CASCADE, db_index=True)
    name = models.CharField(max_length=50)
    introduction = models.TextField(max_length=500, default='')       # 新：替代 profile（展示用）
    system_prompt = models.TextField(max_length=10000, default='')    # 新：LLM 系统提示词
    photo = models.ImageField(upload_to=photo_upload_to)
    voice = models.ForeignKey(Voice, default=None, on_delete=models.CASCADE, blank=True, null=True)
    background_image = models.ImageField(upload_to=background_image_upload_to)
    created_at = models.DateTimeField(auto_now_add=True)              # default=now → auto_now_add
    updated_at = models.DateTimeField(auto_now=True)                  # default=now → auto_now

    @property
    def photo_url(self):
        try: return self.photo.url
        except ValueError: return ''

    @property
    def background_image_url(self):
        try: return self.background_image.url
        except ValueError: return ''

    def __str__(self):
        return f"{self.author.user.username} - {self.name} - {localtime(self.created_at).strftime('%Y-%m-%d %H:%M:%S')}"
```

注意：删除 `profile` 字段，新增 `introduction` + `system_prompt`。

- [ ] **Step 3: 修改 friend.py — Friend 唯一约束 + 索引**

```python
class Friend(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    character = models.ForeignKey(Character, on_delete=models.CASCADE)
    memory = models.TextField(default='', max_length=5000, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['user_profile', 'character']]
        indexes = [models.Index(fields=['user_profile'])]
```

- [ ] **Step 4: 修改 friend.py — Message JSONField + 索引**

```python
class Message(models.Model):
    friend = models.ForeignKey(Friend, on_delete=models.CASCADE)
    user_message = models.TextField(max_length=5000)
    input = models.JSONField(max_length=50000, default=dict)     # TextField → JSONField
    output = models.TextField(max_length=50000)                   # 不变
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)          # default=now → auto_now_add

    class Meta:
        indexes = [models.Index(fields=['friend', '-created_at'])]
```

- [ ] **Step 5: 修改 friend.py — SystemPrompt choices + auto_now**

```python
class SystemPrompt(models.Model):
    class Title(models.TextChoices):
        REPLY = 'reply', '回复'
        MEMORY = 'memory', '记忆'

    title = models.CharField(max_length=20, choices=Title.choices)
    order_number = models.IntegerField(default=0)
    prompt = models.TextField(max_length=10000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

- [ ] **Step 6: 创建 document.py — DocumentChunk 模型**

新文件 `backend/web/models/document.py`：

```python
from django.db import models
from pgvector.django import VectorField


class DocumentChunk(models.Model):
    content = models.TextField()
    embedding = VectorField(dimensions=1024)
    created_at = models.DateTimeField(auto_now_add=True)
```

- [ ] **Step 7: 提交模型变更**

```bash
git add backend/web/models/
git commit -m "feat: refactor models — profile split, indexes, choices, JSONField, DocumentChunk"
```

---

### Task 3: settings.py 切 PostgreSQL

**Files:**
- Modify: `backend/backend/settings.py`

- [ ] **Step 1: 修改 DATABASES 配置**

将第 79-84 行替换为：

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'aifriends',
        'USER': 'aifriends',
        'PASSWORD': 'aifriends001#',
        'HOST': '115.190.245.146',
        'PORT': '5432',
    }
}
```

- [ ] **Step 2: 验证连接 — 确认 Django 能连接 PG**

```bash
cd backend && conda run -n py312 python manage.py check
```

Expected: "System check identified no issues (0 silenced)."

- [ ] **Step 3: 生成并执行 migration**

```bash
conda run -n py312 python manage.py makemigrations
conda run -n py312 python manage.py migrate
```

Expected: 所有 migration 成功执行。

- [ ] **Step 4: Commit**

```bash
git add backend/backend/settings.py backend/web/migrations/
git commit -m "feat: switch to PostgreSQL 17 + apply model migrations"
```

---

### Task 4: 后端视图适配 profile 拆分

**Files:**
- Modify: `backend/web/views/friend/message/chat/chat.py`
- Modify: `backend/web/views/create/character/create.py`
- Modify: `backend/web/views/create/character/update.py`
- Modify: `backend/web/views/create/character/get_single.py`
- Modify: `backend/web/views/create/character/get_list.py`
- Modify: `backend/web/views/friend/get_list.py`
- Modify: `backend/web/views/friend/get_or_create.py`
- Modify: `backend/web/views/homepage/index.py`

- [ ] **Step 1: chat/chat.py — LLM 用 system_prompt**

第 56 行：

```python
prompts.append(f'\n\n【角色性格】\n\n{friend.character.system_prompt}\n')
```

- [ ] **Step 2: create.py — 读 introduction + system_prompt**

第 20-22 行区域：

```python
user_profile = UserProfile.objects.get(user=user)
name = request.data.get('name').strip()
introduction = request.data.get('introduction', '').strip()
system_prompt = request.data.get('system_prompt', '').strip()
```

第 28-32 行验证区：

```python
if not introduction:
    return Response({'message': '角色简介不能为空'}, status=status.HTTP_400_BAD_REQUEST)
if not system_prompt:
    return Response({'message': '角色信息不能为空'}, status=status.HTTP_400_BAD_REQUEST)
```

第 42-44 行创建：

```python
character = Character.objects.create(
    author=user_profile, name=name,
    introduction=introduction, system_prompt=system_prompt,
    photo=photo, background_image=background_image, voice=voice
)
```

- [ ] **Step 3: update.py — 同 create**

第 22-24 行区域：

```python
introduction = request.data.get('introduction', '').strip()
system_prompt = request.data.get('system_prompt', '').strip()
```

验证：

```python
if not introduction:
    return Response({'message': '角色简介不能为空'}, ...)
if not system_prompt:
    return Response({'message': '角色信息不能为空'}, ...)
```

赋值：

```python
character.introduction = introduction
character.system_prompt = system_prompt
```

- [ ] **Step 4: get_single.py — 返回两个字段**

第 30-37 行：

```python
'character': {
    'id': character.id,
    'name': character.name,
    'introduction': character.introduction,
    'system_prompt': character.system_prompt,
    'photo': character.photo_url,
    'background_image': character.background_image_url,
    'voice_id': character.voice.id,
},
```

- [ ] **Step 5: 列表接口 — 返回 introduction 替代 profile**

4 个文件，每个将 `'profile': character.profile` 替换为 `'introduction': character.introduction`：

- `create/character/get_list.py` 第 31 行
- `friend/get_list.py` 第 33 行
- `friend/get_or_create.py` 第 43 行
- `homepage/index.py` 第 31 行

- [ ] **Step 6: Commit**

```bash
git add backend/web/views/
git commit -m "refactor: adapt views to profile split (introduction + system_prompt)"
```

---

### Task 5: pgvector 代码

**Files:**
- Modify: `backend/web/views/friend/message/chat/graph.py`
- Modify: `backend/web/documents/utils/insert_documents.py`

- [ ] **Step 1: 重写 search_knowledge_base**

`graph.py` 第 34-48 行，替换为：

```python
@tool
def search_knowledge_base(query: str) -> str:
    """
    当用户查询"阿里云百炼"相关简介信息时，调用此函数。
    :param query: 要查询的问题
    :return: 查询结果
    """
    from web.documents.utils.custom_embeddings import CustomEmbeddings
    from web.models.document import DocumentChunk

    embeddings = CustomEmbeddings()
    emb = embeddings.embed_query(query)
    chunks = DocumentChunk.objects.raw(
        "SELECT id, content FROM document_chunk ORDER BY embedding <=> %s::vector LIMIT 3",
        [emb]
    )
    context = '\n\n'.join([f'内容片段：{i+1}\n{c.content}' for i, c in enumerate(chunks)])
    return f'从知识库中找到以下相关信息：\n\n{context}\n\n'
```

同时删除顶部的 LanceDB 相关 import（`import lancedb` 和 `from langchain_community.vectorstores import LanceDB`）。

- [ ] **Step 2: 重写 insert_documents.py**

```python
import logging
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from web.documents.utils.custom_embeddings import CustomEmbeddings
from web.models.document import DocumentChunk

logger = logging.getLogger(__name__)


def insert_documents():
    loader = TextLoader('./web/documents/Bailian_Overview.txt', encoding='utf-8')
    docs = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = text_splitter.split_documents(docs)
    logger.info('已切分成 %d 个片段', len(chunks))

    embeddings = CustomEmbeddings()

    DocumentChunk.objects.all().delete()  # 清旧数据再插入（幂等）
    for chunk in chunks:
        emb = embeddings.embed_query(chunk.page_content)
        DocumentChunk.objects.create(content=chunk.page_content, embedding=emb)

    logger.info('已插入 %d 条向量记录', len(chunks))
```

- [ ] **Step 3: Commit**

```bash
git add backend/web/views/friend/message/chat/graph.py backend/web/documents/utils/insert_documents.py
git commit -m "feat: switch knowledge base from LanceDB to pgvector"
```

---

### Task 6: 前端适配 profile 拆分

**Files:**
- Modify: `frontend/src/components/character/CharacterDetail.vue`
- Modify: `frontend/src/components/character/Character.vue`
- Modify: `frontend/src/views/create/character/CreateCharacter.vue`
- Modify: `frontend/src/views/create/character/UpdateCharacter.vue`
- Modify: `frontend/src/views/create/character/components/Profile.vue`

- [ ] **Step 1: CharacterDetail.vue — introduction 替换 profile**

第 92 行：

```html
<p class="text-base whitespace-pre-wrap leading-relaxed">{{ character.introduction }}</p>
```

原来的 `character.profile.split('\n')[0]` 不再需要。

- [ ] **Step 2: Character.vue — introduction**

第 118 行：

```html
{{ character.introduction }}
```

- [ ] **Step 3: CreateCharacter.vue — 新增 system_prompt 字段**

新增一个 SystemPrompt 组件引用，仿照 Profile 组件（textarea + ref）：

在第 5 行附近加 import：

```typescript
import SystemPrompt from "@/views/create/character/components/SystemPrompt.vue";
```

在 template 中 Profile 后加 SystemPrompt 组件：

```html
<Profile ref="profile-ref"/>
<SystemPrompt ref="system-prompt-ref"/>
```

`handleCreate()` 中读两个字段：

```typescript
const systemPromptRef = useTemplateRef('system-prompt-ref')
// ...
const introduction = profileRef.value.myProfile?.trim()
const systemPrompt = systemPromptRef.value.myValue?.trim()
// ...
} else if (!systemPrompt) {
    errorMessage.value = '角色信息不能为空'
}
```

formData 中：

```typescript
formData.append('introduction', introduction)
formData.append('system_prompt', systemPrompt)
```

注意：`profile` → `introduction`，新增 `system_prompt`。

- [ ] **Step 4: 创建 SystemPrompt.vue 组件**

新文件 `frontend/src/views/create/character/components/SystemPrompt.vue`：

```vue
<script setup lang="ts">
import {ref, watch} from "vue";

const props = defineProps(['systemPrompt'])
const myValue = ref(props.systemPrompt)

watch(() => props.systemPrompt, newVal => {
  myValue.value = newVal
})

defineExpose({myValue})
</script>

<template>
  <fieldset class="fieldset">
    <legend class="fieldset-legend">角色信息（发送给 AI）</legend>
    <textarea v-model="myValue" rows="8" class="textarea w-108"
              placeholder="详细的角色性格、语气、行为规则等，将发送给 AI 作为系统提示词"/>
  </fieldset>
</template>
```

- [ ] **Step 5: UpdateCharacter.vue — 同上模式**

与 CreateCharacter.vue 相同的改动：
- import SystemPrompt 组件
- template 中加 `<SystemPrompt ref="system-prompt-ref" :system-prompt="character.system_prompt"/>`
- `handleUpdate()` 中读 `introduction` + `system_prompt`，formData 中对应修改

第 110 行 Profile 的 prop 改为 `:profile="character.introduction"`。

- [ ] **Step 6: Profile.vue 标签文字调整**

Legend 改为 "角色简介"（展示给用户的简短介绍，不再是发送给 AI 的）。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat: adapt frontend to profile split (introduction + system_prompt)"
```

---

### Task 7: 测试适配

**Files:**
- Modify: `backend/web/tests/test_character.py`

- [ ] **Step 1: 修改 test_character.py**

将所有 `character.profile` → `character.introduction`（第 113 行附近）。

`test_update_success` 中更新断言：

```python
assert character.introduction == "Updated profile"
```

- [ ] **Step 2: 更新 test_character.py 的创建测试**

`test_create_success` 中 formData 的 `'profile'` → `'introduction'`：

```python
resp = auth_client.post(
    "/api/create/character/create/",
    {
        "name": "My Character",
        "introduction": "A friendly AI",
        "system_prompt": "You are a friendly AI character...",
        "voice_id": voice.id,
        "photo": _make_test_image("photo.jpg"),
        "background_image": _make_test_image("bg.jpg"),
    },
)
```

- [ ] **Step 3: Commit**

```bash
git add backend/web/tests/test_character.py
git commit -m "test: update character tests for profile split"
```

---

### Task 8: 迁移执行 + 全量测试验证

- [ ] **Step 1: 执行 makemigrations + migrate**

```bash
cd backend
conda run -n py312 python manage.py makemigrations
conda run -n py312 python manage.py migrate
```

- [ ] **Step 2: 运行全量测试**

```bash
conda run -n py312 python -m pytest web/tests/ -v
```

Expected: 48 passed（所有测试通过 PostgreSQL）。

- [ ] **Step 3: 插入知识库文档**

```bash
conda run -n py312 python manage.py shell -c "
from web.documents.utils.insert_documents import insert_documents
insert_documents()
"
```

- [ ] **Step 4: 验证向量检索**

```bash
conda run -n py312 python manage.py shell -c "
from web.models.document import DocumentChunk
from web.documents.utils.custom_embeddings import CustomEmbeddings
e = CustomEmbeddings()
emb = e.embed_query('什么是百炼')
chunks = DocumentChunk.objects.raw(
    'SELECT id, content FROM document_chunk ORDER BY embedding <=> %s::vector LIMIT 3', [emb]
)
for c in chunks:
    print(c.content[:80])
"
```

Expected: 输出知识库内容片段。

- [ ] **Step 5: Commit（如有调整）**

```bash
git add -A
git commit -m "chore: finalize PostgreSQL migration"
```

---

## 约束与注意事项

1. **分支隔离** — 所有改动在 `feature/gqyin/postgresql-migration` 分支，master 不变
2. **SQLite 旧数据** — 已舍弃，不对旧数据进行迁移
3. **LanceDB** — 代码和 lancedb_storage/ 目录保留不删
4. **Voice.profile / UserProfile.profile** — 不与 Character.profile 混淆，这些不变
5. **Migration 顺序** — Django 按文件数字前缀执行，新 migration 自动依赖最新的
6. **前端改动** — `profile` 字段在 JSON 响应中已被替换，确保前后端同步部署
