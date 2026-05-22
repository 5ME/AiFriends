# AI Friends — PostgreSQL 迁移设计

> 日期：2026-05-17 | 基准分支：master (3b1868d) | 实施分支：`feature/gqyin/postgresql-migration`
> 运行环境：conda `py312`

## 一、目标

SQLite → PostgreSQL 17.10 + pgvector 0.8.2，同步完成模型优化和向量库切换。

**本次做：**
- settings.py 切 PostgreSQL
- 模型优化：索引/约束 + choices + auto_now + `input`→JSONField + profile 拆分
- pgvector 替换 LanceDB：新增 DocumentChunk + 重写 insert_documents + 重写 search_knowledge_base
- 前后端适配 profile 拆分

**本次不做：**
- 删除 LanceDB 代码/lancedb_storage/（保留不动）
- 阿里云 OSS

## 二、模型改动

### Character — profile 拆分 + 索引

`profile` → `introduction`（展示用，~500字）+ `system_prompt`（LLM用，~10000字）。两字段完全独立，LLM 只用 `system_prompt`。`author` 加 `db_index=True`。

```python
class Character(models.Model):
    author = models.ForeignKey(UserProfile, on_delete=models.CASCADE, db_index=True)
    name = models.CharField(max_length=50)
    introduction = models.TextField(max_length=500, default='')
    system_prompt = models.TextField(max_length=10000, default='')
    photo = models.ImageField(upload_to=photo_upload_to)
    voice = models.ForeignKey(Voice, ...)
    background_image = models.ImageField(upload_to=background_image_upload_to)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

### Voice — auto_now

```python
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)   # 新
```

### Friend — 唯一约束 + 索引

```python
    class Meta:
        unique_together = [['user_profile', 'character']]
        indexes = [models.Index(fields=['user_profile'])]
```

### Message — JSONField + 索引

`input`→JSONField。`output` 保持 TextField（LLM 返回的是纯文本拼接，非 JSON）。

```python
    input = models.JSONField(max_length=50000, default=dict)
    output = models.TextField(max_length=5000)

    class Meta:
        indexes = [models.Index(fields=['friend', '-created_at'])]
```

### SystemPrompt — choices + auto_now

```python
    class Title(models.TextChoices):
        REPLY = 'reply', '回复'
        MEMORY = 'memory', '记忆'

    title = models.CharField(max_length=20, choices=Title.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

### DocumentChunk — 新增

```python
# 新文件: web/models/document.py
from pgvector.django import VectorField

class DocumentChunk(models.Model):
    content = models.TextField()
    embedding = VectorField(dimensions=1024)
    created_at = models.DateTimeField(auto_now_add=True)
```

## 三、后端视图改动

### 3.1 chat/chat.py — LLM 系统提示词

```python
# add_system_prompt() 中
prompts.append(f'\n\n【角色性格】\n\n{friend.character.system_prompt}\n')
# 原: friend.character.profile
```

### 3.2 角色创建/编辑 — 读两个字段

`create.py` / `update.py`：`request.data.get('profile')` → `request.data.get('introduction')` + `request.data.get('system_prompt')`

### 3.3 角色详情 — 返回两个字段

`get_single.py`：返回 `introduction` + `system_prompt`（编辑页预填需要两者）

### 3.4 列表接口 — 只返回 introduction

| 文件 | 改动 |
|------|------|
| `create/character/get_list.py` | 返回 `introduction` |
| `friend/get_list.py` | 返回 `introduction` |
| `friend/get_or_create.py` | 返回 `introduction` |
| `homepage/index.py` | 返回 `introduction` |

列表场景不需要 10000 字的 system_prompt，只返回 introduction 避免撑大 payload。

### 3.5 不改的 profile 引用

以下属于 **Voice** 或 **UserProfile** 模型，与 Character.profile 拆分无关：

> `voice.profile`、`user_profile.profile`、UserProfile 相关视图

## 四、前端改动

| 文件 | 改动 |
|------|------|
| `CharacterDetail.vue:92` | `character.profile.split('\n')[0]` → `character.introduction` |
| `Character.vue:118` | `character.profile` → `character.introduction` |
| `CreateCharacter.vue` | `profile` 字段 → `introduction` + `system_prompt` 两个 textarea |
| `UpdateCharacter.vue` | 同上，预填从 `introduction`/`system_prompt` 取值 |

## 五、pgvector 代码

### 5.1 重写 search_knowledge_base

```python
@tool
def search_knowledge_base(query: str) -> str:
    embeddings = CustomEmbeddings()
    emb = embeddings.embed_query(query)
    chunks = DocumentChunk.objects.raw(
        "SELECT id, content FROM document_chunk ORDER BY embedding <=> %s::vector LIMIT 3",
        [emb]
    )
    context = '\n\n'.join([f'内容片段：{i+1}\n{c.content}' for i, c in enumerate(chunks)])
    return f'从知识库中找到以下相关信息：\n\n{context}\n\n'
```

### 5.2 重写 insert_documents.py

保留 `TextLoader` + `RecursiveCharacterTextSplitter`（它们不依赖 LanceDB），插入目标改为 Django ORM：

```python
def insert_documents():
    ...
    for chunk in chunks:
        emb = embeddings.embed_query(chunk.page_content)
        DocumentChunk.objects.create(content=chunk.page_content, embedding=emb)
```

## 六、依赖

```diff
# requirements.txt
+ psycopg2-binary>=2.9
+ django-pgvector>=0.1
```

## 七、settings.py

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

## 八、测试适配

`test_character.py`：`character.profile` → `character.introduction`（受模型变更影响）

## 九、验证

```bash
conda run -n py312 pip install psycopg2-binary django-pgvector
cd backend
conda run -n py312 python manage.py makemigrations
conda run -n py312 python manage.py migrate
conda run -n py312 python -m pytest web/tests/ -v     # 48 passed
# 知识库插入 + 检索验证
conda run -n py312 python manage.py shell -c "..."
```
