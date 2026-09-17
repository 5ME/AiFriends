# 音色自定义（一期 · A+B 批）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修掉音色链路的 4 处隐患、把 `voice_id`/`voice` 命名统一，并给音色加上试听。

**Architecture:** `Character.voice` 的删除语义从 `CASCADE` 改为 `RESTRICT`（删被引用的音色被拒，但不阻断"删用户"这条级联路径 —— `PROTECT` 会阻断）；`Voice.voice_id` 加字符集校验器（Admin 表单路径生效）；三个 view 对齐 404/400 口径并统一用 `voice` 作为字段名，重复的序列化抽成一个共用函数；新增一个一次性 TTS 合成工具与一个试听端点，样音按 `sha256(文案)[:8]` 落盘到 MEDIA 永久缓存，失败写 60 秒负缓存。

**Tech Stack:** Django 6.0.2 / DRF / pytest + pytest-django / 阿里云 DashScope WebSocket TTS（`cosyvoice-v3-flash`）/ Vue 3 + Vitest

**Spec:** `docs/superpowers/specs/2026-09-13-voice-customization-design.md`

## Global Constraints

- **分支**：`feature/gqyin/voice-customization`。不在 master 上提交。
- **状态码口径**（spec §5）：**404** = 这个音色对你来说不存在（不存在、他人的私有音色，且两种 message 必须逐字相同）；**400** = 可见但当下不能用（`status != 'ready'`、参数不合法、配额、被角色引用）；**503** = 上游不可用或超时。
- **超时**：请求路径上的阻塞外部调用一律 5 秒超时，超时归入 503。
- **异常**：不裸 `except`；一律 `except Exception as e:` + `logger.exception(...)`。
- **视图模式**：每个端点一个文件、一个 `APIView`，不用 DRF serializer，直接读 `request.data`。
- **后端测试**：`cd backend && D:/MyWork/Miniconda3/envs/py312/python.exe -m pytest web/tests/ -v`
  基线 **236 passed, 3 deselected**（`pytest.ini` 默认 `-m "not slow"`）。
- **前端测试**：`cd frontend && npm run test:unit`
- **范围冻结**（spec §5）：不新增 spec §5 表以外的接口或字段。**`owner` / `visibility` / `status` 三个字段属于 C 批**，本批不引入。
- **本批的顺序调整（四处，提 PR 时必须写明，否则 门 4 会对不上账）**：spec §9 里的 **A5**（`status != 'ready'` → 400）、**A6**（他人的私有音色 → 404 且 message 与"不存在"逐字相同）、**B3 的后半**（非 ready 音色试听 → 400 且不打阿里云）、**B7**（非 ready 音色禁用播放按钮）都依赖 `status` / `owner` 字段，而这两个字段属 C 批，因此这四项随 C 批实现。**后果：spec §10 的 A 批验收里"可见但 `status != 'ready'` → 400"这一条在 A+B 批勾不了。**
  - 附带说明：A6 要求的"message 同一性"在 A+B 里只有一个 404 分支，天然满足；真正的守门（存在但不可见 → 同一个 message）落在 C 批。
- **spec §5 里 get_list 的 `sample_url` 字段本批不实现**：前端点击试听时直接调 sample 端点即可拿到 URL，列表再带一个 `sample_url` 会多出第二条代码路径（"有 URL 直接播" vs "没 URL 先请求"），属于无收益的复杂度。

---

### Task 0: 建分支并提交 spec 与 plan

**Files:**
- Add: `docs/superpowers/specs/2026-09-13-voice-customization-design.md`（已在工作区，untracked）
- Add: `docs/superpowers/plans/2026-09-16-voice-customization-a-plus-b.md`（本文件）

- [ ] **Step 1: 建分支**

```bash
git checkout -b feature/gqyin/voice-customization
```

- [ ] **Step 2: 提交两份文档**

```bash
git add docs/superpowers/specs/2026-09-13-voice-customization-design.md \
        docs/superpowers/plans/2026-09-16-voice-customization-a-plus-b.md
git commit -m "docs(voice): 音色自定义一期设计文档与 A+B 批实施计划"
```

Expected: `git status --short` 除这两份文档外无其他条目（开工前已确认工作区干净）。

---

### Task 1: 模型层 —— `RESTRICT` + `Voice.voice_id` 校验器

**Files:**
- Modify: `backend/web/models/character.py`
- Create: `backend/web/migrations/0023_*.py`（`makemigrations` 生成）
- Test: `backend/web/tests/test_voice_integrity.py`（新建）

**Interfaces:**
- Produces: 删被角色引用的 `Voice` → 抛 `django.db.models.RestrictedError`；删用户（经 `UserProfile` CASCADE 带走角色）**不**受阻断；`Voice.voice_id` 带字符集校验器（`full_clean()` / Admin 表单生效）。

- [ ] **Step 1: 写失败测试**

新建 `backend/web/tests/test_voice_integrity.py`：

```python
import pytest
from django.core.exceptions import ValidationError
from django.db.models import RestrictedError

from web.models.character import Character, Voice


class TestVoiceDeleteSemantics:
    """A8 / A9：RESTRICT 的语义与守门"""

    def test_delete_referenced_voice_is_restricted(self, character, voice):
        """删被角色引用的音色 → 被拒，且角色完好（现状会被级联删掉）"""
        with pytest.raises(RestrictedError):
            voice.delete()
        assert Character.objects.filter(id=character.id).exists()

    def test_delete_unused_voice_succeeds(self, voice):
        """无人使用的音色仍可删除（clean_dirty_characters 依赖这条）"""
        vid = voice.id
        voice.delete()
        assert not Voice.objects.filter(id=vid).exists()

    def test_delete_user_with_character_does_not_raise(self, user, character):
        """A9 守门：RESTRICT 不应阻断"删用户→级联删角色"这条路径（PROTECT 会阻断）"""
        user.delete()
        assert not Character.objects.filter(id=character.id).exists()


class TestVoiceIdValidator:
    def test_valid_ids_pass_full_clean(self):
        """线上三个真实标识与测试夹具都必须通过"""
        for vid in ('longanyang', 'longanhuan', 'test_voice_001',
                    'cosyvoice-v3-flash-guanyin-f7af6ea4c9f947cf887c1f5f655b7d99'):
            Voice(name='x', voice_id=vid).full_clean()

    def test_rejects_ids_with_space_or_non_ascii(self):
        for bad in ('has space', '中文音色', '-leading-dash', ''):
            with pytest.raises(ValidationError):
                Voice(name='x', voice_id=bad).full_clean()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && D:/MyWork/Miniconda3/envs/py312/python.exe -m pytest web/tests/test_voice_integrity.py -v`
Expected:
- `test_delete_referenced_voice_is_restricted` **FAIL**（当前 `CASCADE`，不抛异常且角色被删）
- `test_delete_user_with_character_does_not_raise` **PASS**（本批它是守门用例，改前也过；C 批引入 `owner` 后再补"音色也被删掉"的断言）
- 两条 validator 用例 **FAIL**

- [ ] **Step 3: 改模型**

`backend/web/models/character.py`：加导入并在两处修改。

```python
from django.core.validators import RegexValidator
```

```python
VOICE_ID_VALIDATOR = RegexValidator(
    r'^[A-Za-z0-9][A-Za-z0-9_-]*$',
    '音色 ID 只能是字母、数字、下划线或连字符',
)


class Voice(models.Model):
    name = models.CharField(max_length=100)
    voice_id = models.CharField(
        max_length=100,
        help_text="阿里云音色ID",
        validators=[VOICE_ID_VALIDATOR],
    )
    profile = models.TextField(max_length=500, default='')
    is_builtin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

```python
    voice = models.ForeignKey(Voice, default=None, on_delete=models.RESTRICT,
                              blank=True, null=True)
```

- [ ] **Step 4: 生成迁移**

Run: `cd backend && D:/MyWork/Miniconda3/envs/py312/python.exe manage.py makemigrations web`
Expected: 生成一个 `0023_alter_character_voice_alter_voice_voice_id.py`，内容只有两条 `AlterField`，**没有任何 `RunPython` / 数据迁移**。

- [ ] **Step 5: 跑测试确认通过**

Run: `... -m pytest web/tests/test_voice_integrity.py -v`
Expected: 5 passed。

- [ ] **Step 6: 提交**

```bash
git add backend/web/models/character.py backend/web/migrations/0023_*.py backend/web/tests/test_voice_integrity.py
git commit -m "fix(voice): 音色删除语义改用 RESTRICT，voice_id 加字符集校验"
```

---

### Task 2: 三个 view —— 错误语义、判空、命名统一、共用序列化

**Files:**
- Create: `backend/web/views/create/character/voice/serializer.py`
- Modify: `backend/web/views/create/character/create.py`
- Modify: `backend/web/views/create/character/update.py`
- Modify: `backend/web/views/create/character/get_single.py`
- Modify: `backend/web/views/create/character/voice/get_list.py`
- Modify: `backend/web/tests/test_character.py`（7 处 `voice_id` → `voice`）
- Test: `backend/web/tests/test_voice_integrity.py`（追加）

**Interfaces:**
- Produces: `serialize_voice(voice) -> dict`，形如 `{'id': int, 'name': str, 'profile': str}`。
- Produces: `POST create/` 与 `update/` 接受表单字段 **`voice`**（不再接受 `voice_id`）；`GET get_single/` 响应里是 `character['voice']`。

- [ ] **Step 1: 写失败测试**

追加到 `backend/web/tests/test_voice_integrity.py`（顶部补 `from io import BytesIO`、`from PIL import Image`、`from django.core.files.uploadedfile import SimpleUploadedFile`、`from rest_framework import status`，以及 `_make_test_image` 助手 —— 直接从 `test_character.py:10-16` 复制）：

```python
class TestVoiceContract:
    """A1–A4、A7：字段名统一为 voice，错误语义分档（A5/A6 依赖 C 批字段，不在此）"""

    def _payload(self, voice_value, **override):
        data = {
            'name': 'n', 'introduction': 'i', 'system_prompt': 's',
            'photo': _make_test_image('photo.jpg'),
            'background_image': _make_test_image('bg.jpg'),
        }
        if voice_value is not None:
            data['voice'] = voice_value
        data.update(override)
        return data

    def test_create_with_unknown_voice_returns_404(self, auth_client, db):
        resp = auth_client.post('/api/create/character/create/',
                                self._payload(999999))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_create_without_voice_returns_400(self, auth_client, db):
        resp = auth_client.post('/api/create/character/create/',
                                self._payload(None))
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_with_garbage_voice_returns_404(self, auth_client, db):
        """非数字 id 不能 500"""
        resp = auth_client.post('/api/create/character/create/',
                                self._payload('not-a-number'))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_update_with_unknown_voice_returns_404(self, auth_client, character):
        resp = auth_client.post('/api/create/character/update/', {
            'character_id': character.id, 'name': 'n',
            'introduction': 'i', 'system_prompt': 's', 'voice': 999999,
        })
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_update_without_voice_returns_400(self, auth_client, character):
        resp = auth_client.post('/api/create/character/update/', {
            'character_id': character.id, 'name': 'n',
            'introduction': 'i', 'system_prompt': 's',
        })
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_single_with_null_voice_returns_200(self, auth_client, character):
        """A7：角色音色为空时不再 500"""
        character.voice = None
        character.save(update_fields=['voice'])
        resp = auth_client.get('/api/create/character/get_single/',
                               {'character_id': character.id})
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()['character']['voice'] is None

    def test_get_single_returns_voice_field_name(self, auth_client, character, voice):
        resp = auth_client.get('/api/create/character/get_single/',
                               {'character_id': character.id})
        body = resp.json()['character']
        assert body['voice'] == voice.id
        assert 'voice_id' not in body

    def test_voice_list_shape(self, auth_client, voice):
        resp = auth_client.get('/api/create/character/voice/get_list/')
        assert resp.status_code == status.HTTP_200_OK
        first = resp.json()['voices'][0]
        assert set(first) == {'id', 'name', 'profile'}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `... -m pytest web/tests/test_voice_integrity.py -v -k TestVoiceContract`
Expected: **除 `test_voice_list_shape` 外全部 FAIL**（`voice` 字段当前不存在 → 落到 400/500；`voice_id` 仍是响应字段名），其中 `test_get_single_with_null_voice_returns_200` 当前应是 **500**。
⚠️ `test_voice_list_shape` 是 **pin 用例**（钉住"列表只回 `id`/`name`/`profile` 三个键"这个现状），所以它在实现前后**都是绿的** —— 看到它是绿的不要以为"改完了"或"改错了"。

- [ ] **Step 3: 新建共用序列化**

`backend/web/views/create/character/voice/serializer.py`：

```python
def serialize_voice(voice):
    """音色对外表示。get_list / get_single 共用一份，避免改一处漏一处。"""
    return {
        'id': voice.id,
        'name': voice.name,
        'profile': voice.profile,
    }
```

- [ ] **Step 4: 改三个 view**

`create.py`：把第 26 行的 `voice_id` 取值与第 44 行的查询替换为：

```python
            voice_pk = request.data.get('voice')
```

```python
            if not voice_pk:
                return Response({'message': '角色音色不能为空'},
                                status=status.HTTP_400_BAD_REQUEST)
            try:
                voice = Voice.objects.get(id=voice_pk)
            except (Voice.DoesNotExist, ValueError, TypeError):
                return Response({'message': '音色不存在或无权访问'},
                                status=status.HTTP_404_NOT_FOUND)
```

（局部变量叫 `voice_pk` 而不是 `voice_id` —— 它存的是 `Voice` 主键，沿用 `voice_id` 就把 spec D4 要消灭的"一名两义"搬到了函数体里；也不叫 `voice`，因为同一函数下面已经有一个 `voice` 对象。）

（`ValueError` / `TypeError` 覆盖"传了非数字 id"这类输入 —— 不做这层捕获就会掉进兜底的 500。）

`update.py`：同样把 `request.data['voice_id']` 改为 `request.data.get('voice')`，并加上与上面相同的 400 / 404 两段（放在 `name`/`introduction`/`system_prompt` 的空值校验之后、`Voice.objects.get` 之前）。
**注意**：同文件第 20 行的 `request.data['character_id']` 保持不动 —— 它属 spec §1.3 登记的"同类问题但不在音色范围"，本批不改。

`get_single.py`：第 41 行改为判空，并让 `voices` 列表走共用函数：

```python
                    'voice': character.voice.id if character.voice else None,
```

```python
            voices_raw = Voice.objects.order_by('id')
            voices = [serialize_voice(v) for v in voices_raw]
```

`voice/get_list.py`：同样把循环替换为 `serialize_voice`，并在该文件顶部加：

```python
from web.views.create.character.voice.serializer import serialize_voice
```

`get_single.py` 顶部同样加这一行 import。

- [ ] **Step 5: 同步既有测试的字段名**

`backend/web/tests/test_character.py` 里 7 处 `"voice_id": voice.id` 全部改为 `"voice": voice.id`（行号约 30、42、54、69、84、126、144）。改完 `grep -n "voice_id" backend/web/tests/test_character.py` 应无输出。

- [ ] **Step 6: 跑测试确认通过**

Run: `... -m pytest web/tests/ -v`
Expected: 全绿（236 + 本批新增条数）。若 `test_character.py` 有红，检查是否漏改了 `voice_id`。

- [ ] **Step 7: 提交**

```bash
git add backend/web/views/create/character/ backend/web/tests/
git commit -m "refactor(voice): 字段名统一为 voice，错误语义分档，抽掉重复序列化"
```

---

### Task 3: 前端跟随契约（`voice_id` → `voice`）

**Files:**
- Modify: `frontend/src/views/create/character/CreateCharacter.vue`
- Modify: `frontend/src/views/create/character/UpdateCharacter.vue`
- Modify: `frontend/src/views/create/character/components/Voice.vue`

**Interfaces:**
- Consumes: Task 2 的接口契约（表单字段 `voice`、`get_single` 返回 `character.voice`）。

- [ ] **Step 1: 改三处字段名**

`CreateCharacter.vue`：
- 第 28 行 `const curVoiceId = ref(null)` → `const curVoice = ref(null)`
- 第 35 行 `curVoiceId.value = response.data.voices[0].id` → `curVoice.value = ...`
- 第 66 行 `formData.append('voice_id', voice)` → `formData.append('voice', voice)`
- 第 97 行 `<Voice ref="voice-ref" :voices="voices" :curVoiceId="curVoiceId"/>` → `:curVoice="curVoice"`

`UpdateCharacter.vue`：
- 第 21 行 `const curVoiceId = ref(null)` → `const curVoice = ref(null)`
- 第 31 行 `curVoiceId.value = response.data.character.voice_id` → `curVoice.value = response.data.character.voice`
- 第 80 行 `formData.append('voice_id', voice)` → `formData.append('voice', voice)`
- 第 115 行 `:curVoiceId="curVoiceId"` → `:curVoice="curVoice"`

`components/Voice.vue`：把 props 与内部命名改为 `curVoice`（`defineProps(["voices", "curVoice"])`、`myVoice` 保留），`defineExpose` 仍暴露 `myVoice`。

- [ ] **Step 2: 手工确认无残留**

Run: `cd frontend && grep -rn "voice_id" src/`
Expected: 无输出。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/create/character/
git commit -m "refactor(voice): 前端字段名跟随接口统一为 voice"
```

---

### Task 4: 后端试听 —— 一次性合成 + 缓存 + 端点

**Files:**
- Create: `backend/web/utils/tts.py`
- Modify: `backend/web/views/friend/message/chat/chat.py`（改用共用常量，payload 不变）
- Create: `backend/web/views/create/character/voice/sample.py`
- Modify: `backend/web/urls.py`
- Test: `backend/web/tests/test_voice_sample.py`（新建）

**Interfaces:**
- Produces: `web.utils.tts` 导出 `TTS_MODEL` / `TTS_FORMAT` / `TTS_SAMPLE_RATE` / `TTS_VOLUME` / `TTS_RATE` / `TTS_PITCH` / `TTS_TIMEOUT_SECONDS` 与 `synthesize_once(text: str, voice_id: str) -> bytes`。
- Produces: `GET /api/create/character/voice/sample/?voice=<id>` → `{'message': 'success', 'url': '<MEDIA_URL>voice_samples/<file>'}`；不可见 → 404；合成失败或超时 → 503。

**协议事实（照 `chat.py` 实测对齐，勿自行发挥）**：发送顺序是 `run-task`（`input` 为空对象）→ 等 `task-started`（文本帧）→ `continue-task` 带 `payload.input.text` → `finish-task`（`input` 为空对象）；**服务端推来的音频是二进制帧**（`chat.py:564` 就是靠 `isinstance(msg, bytes)` 判定的），文本帧里 `task-finished` / `task-failed` 表示结束。

- [ ] **Step 1: 写失败测试**

新建 `backend/web/tests/test_voice_sample.py`：

```python
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings
from rest_framework import status

SAMPLE_PATH = 'web.views.create.character.voice.sample.synthesize_once'


@pytest.fixture(autouse=True)
def _clean_sample_cache():
    """media_root 是 session 级（conftest.py:27），样音缓存会跨用例残留；
    而 voice 夹具的 voice_id 固定为 test_voice_001，缓存键也就固定 —— 必须每例清空。"""
    samples = Path(settings.MEDIA_ROOT) / 'voice_samples'
    if samples.exists():
        shutil.rmtree(samples)
    yield


class TestVoiceSample:
    """`user` 夹具本身就会创建 UserProfile（`conftest.py:58-63`），`auth_client` 依赖它，
    所以视图里的 `request.user.userprofile` 在任何用 `auth_client` 的用例里都成立
    —— 不需要额外要 `user_profile` 夹具（`test_asr.py` 的同一模式已在跑）。"""

    def test_first_request_synthesizes_and_returns_url(self, auth_client, voice):
        with patch(SAMPLE_PATH, return_value=b'ID3fakeaudio') as m:
            resp = auth_client.get('/api/create/character/voice/sample/',
                                   {'voice': voice.id})
        assert resp.status_code == status.HTTP_200_OK
        url = resp.json()['url']
        assert url.startswith(settings.MEDIA_URL)   # 生产是绝对地址，见 Step 3 的说明
        assert 'voice_samples/' in url and url.endswith('.mp3')
        assert m.call_count == 1

    def test_second_request_hits_cache(self, auth_client, voice):
        """B2：第二次不再触发合成"""
        with patch(SAMPLE_PATH, return_value=b'ID3fakeaudio') as m:
            auth_client.get('/api/create/character/voice/sample/', {'voice': voice.id})
            resp = auth_client.get('/api/create/character/voice/sample/', {'voice': voice.id})
        assert resp.status_code == status.HTTP_200_OK
        assert m.call_count == 1

    def test_unknown_voice_returns_404(self, auth_client, db):
        resp = auth_client.get('/api/create/character/voice/sample/', {'voice': 999999})
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_synthesis_failure_returns_503(self, auth_client, voice):
        with patch(SAMPLE_PATH, side_effect=RuntimeError('boom')):
            resp = auth_client.get('/api/create/character/voice/sample/',
                                   {'voice': voice.id})
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_failure_writes_negative_cache(self, auth_client, voice):
        """B4：失败后短时间内不再打上游"""
        with patch(SAMPLE_PATH, side_effect=RuntimeError('boom')) as m:
            auth_client.get('/api/create/character/voice/sample/', {'voice': voice.id})
            resp = auth_client.get('/api/create/character/voice/sample/', {'voice': voice.id})
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert m.call_count == 1

    def test_records_usage_user_id_is_userprofile_id(self, auth_client, user, voice, db):
        """B1 的关键断言：`APIUsage.user_id` 必须是 **UserProfile.id**。

        ⚠️ 只断言 `user_id == user_profile.id` 是不够的：默认夹具下两者可能恰好相等，
        那样即使代码误传 `request.user.id`（auth User 的 PK）也会通过。所以照
        `test_asr.py:106` 的既有做法强制两个 id 分叉，让这条断言真正有区分力。
        """
        from django.contrib.auth.models import User
        from web.models.user import UserProfile

        # 先建 dummy 推进自增序列，再删掉重建测试用户的 profile → 新 id ≠ user.id
        dummy = User.objects.create_user(username='voice_sample_dummy')
        UserProfile.objects.create(user=dummy)
        UserProfile.objects.get(user=user).delete()
        new_up = UserProfile.objects.create(user=user)
        assert user.id != new_up.id, '前置条件失败：User.id 应不等于 UserProfile.id'

        with patch(SAMPLE_PATH, return_value=b'ID3fakeaudio'), \
             patch('web.views.create.character.voice.sample.record_api_usage') as rec:
            auth_client.get('/api/create/character/voice/sample/', {'voice': voice.id})
        assert rec.call_count == 1
        assert rec.call_args.kwargs['api_type'] == 'tts'
        assert rec.call_args.kwargs['update_quota'] is False
        assert rec.call_args.kwargs['user_id'] == new_up.id


class TestSynthesizeOnceTimeout:
    """B5：超时纪律的守门 —— 上游挂住时必须抛 TimeoutError，不能无限等"""

    def test_timeout_raises(self, monkeypatch):
        import asyncio

        from web.utils import tts

        async def _slow(text, voice_id):
            await asyncio.sleep(30)

        monkeypatch.setattr(tts, '_synthesize_once_async', _slow)
        monkeypatch.setattr(tts, 'TTS_TIMEOUT_SECONDS', 0.1)
        with pytest.raises(TimeoutError):      # 3.11+ 起 asyncio.TimeoutError 即内置 TimeoutError
            tts.synthesize_once('你好', 'test_voice_001')
```

- [ ] **Step 2: 跑测试确认失败**

Run: `... -m pytest web/tests/test_voice_sample.py -v`
Expected: **除 `test_unknown_voice_returns_404` 外全部 FAIL**（URL 未注册 → import 失败 / 404）。
⚠️ `test_unknown_voice_returns_404` 在实现前**也是绿的，但原因不同**：URL 还没注册，Django 返回的是自己的 404。实现后它绿的原因才变成"视图主动返回 404"。**Step 6 的全量通过才是它绿得对的凭据**，不要只看这一条的颜色。

- [ ] **Step 3: 新建共用 TTS 工具**

`backend/web/utils/tts.py`：

```python
"""DashScope 语音合成的共用常量与"一次性合成"。

聊天主链路（chat.py）与音色试听共用同一组参数，保证"试听到的"等于"聊天听到的"。
音频以二进制帧返回（chat.py 依靠 isinstance(msg, bytes) 判定），这里直接拼接落盘。
"""
import asyncio
import json
import os
import uuid

import websockets

TTS_MODEL = 'cosyvoice-v3-flash'
TTS_FORMAT = 'mp3'
TTS_SAMPLE_RATE = 22050
TTS_VOLUME = 50
TTS_RATE = 1.0
TTS_PITCH = 1
TTS_TIMEOUT_SECONDS = 5


def _run_task_payload(task_id, voice_id):
    return {
        'header': {'action': 'run-task', 'task_id': task_id, 'streaming': 'duplex'},
        'payload': {
            'task_group': 'audio',
            'task': 'tts',
            'function': 'SpeechSynthesizer',
            'model': TTS_MODEL,
            'parameters': {
                'text_type': 'PlainText',
                'voice': voice_id,
                'format': TTS_FORMAT,
                'sample_rate': TTS_SAMPLE_RATE,
                'volume': TTS_VOLUME,
                'rate': TTS_RATE,
                'pitch': TTS_PITCH,
            },
            'input': {},
        },
    }


async def _synthesize_once_async(text, voice_id):
    wss_url = os.getenv('WSS_URL')
    api_key = os.getenv('API_KEY')
    task_id = uuid.uuid4().hex
    chunks = []
    async with websockets.connect(
            wss_url,
            additional_headers={'Authorization': f'Bearer {api_key}'},
            open_timeout=TTS_TIMEOUT_SECONDS) as ws:
        await ws.send(json.dumps(_run_task_payload(task_id, voice_id)))
        async for msg in ws:                      # 等 task-started
            if isinstance(msg, bytes):
                continue
            if json.loads(msg)['header']['event'] == 'task-started':
                break
        for action, payload in (('continue-task', {'input': {'text': text}}),
                                ('finish-task', {'input': {}})):
            await ws.send(json.dumps({
                'header': {'action': action, 'task_id': task_id, 'streaming': 'duplex'},
                'payload': payload,
            }))
        async for msg in ws:
            if isinstance(msg, bytes):
                chunks.append(msg)
                continue
            event = json.loads(msg)['header']['event']
            if event == 'task-failed':
                raise RuntimeError('TTS task-failed')
            if event == 'task-finished':
                break
    if not chunks:
        raise RuntimeError('TTS 未返回任何音频')
    return b''.join(chunks)


def synthesize_once(text, voice_id):
    """同步入口：跑一次完整合成，超时抛 TimeoutError。调用方负责转成 503。"""
    return asyncio.run(asyncio.wait_for(_synthesize_once_async(text, voice_id),
                                        timeout=TTS_TIMEOUT_SECONDS))
```

（落盘的是**原始 mp3 字节**，不需要 base64 —— `chat.py:565` 之所以 base64 是为了塞进 SSE；这里直接拼二进制。另外 `settings.MEDIA_URL` 在生产是**绝对地址**：实测服务器容器里的 `DJANGO_MEDIA_URL` 为 `https://8.153.201.12/media/`（`.env.example:35` 也要求显式配置），所以拼出来的 URL 前端可直接播放，不需要再加前缀。）

- [ ] **Step 4: 让 chat.py 用共用常量**

`chat.py:419-427` 那段 `parameters` 里的六个字面量换成 `web.utils.tts` 的常量（`TTS_MODEL` / `TTS_FORMAT` / `TTS_SAMPLE_RATE` / `TTS_VOLUME` / `TTS_RATE` / `TTS_PITCH`），`:549` 的 `'model_name': 'cosyvoice-v3-flash'` 换成 `TTS_MODEL`。
**只换字面量，不动 `tts_sender` / `tts_receiver` 的任何逻辑** —— 那是聊天主链路，重构收益不抵风险。
验证：`... -m pytest web/tests/test_chat_agent.py -v` 全绿。

- [ ] **Step 5: 新建试听端点**

`backend/web/views/create/character/voice/sample.py`：

```python
import hashlib
import logging
import time
from pathlib import Path

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.character import Voice
from web.utils.tts import TTS_MODEL, synthesize_once
from web.utils.usage import record_api_usage

logger = logging.getLogger(__name__)

SAMPLE_TEXT_TEMPLATE = '你好呀，我是{}，很高兴认识你。'
SAMPLE_NAME_MAX_LEN = 20          # 音色名会被拼进 TTS 文案，截断防止成本随用户输入膨胀
NEGATIVE_CACHE_SECONDS = 60       # 失败后在窗口内不再打上游
SAMPLE_DIR_NAME = 'voice_samples'


def build_sample_text(voice_name):
    return SAMPLE_TEXT_TEMPLATE.format((voice_name or '')[:SAMPLE_NAME_MAX_LEN])


def _sample_dir():
    return Path(settings.MEDIA_ROOT) / SAMPLE_DIR_NAME


def sample_cache_path(voice_id, text):
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]
    return _sample_dir() / f'{voice_id}-{digest}.mp3'


def _negative_cache_active(path):
    marker = path.with_suffix(path.suffix + '.fail')
    return marker.exists() and (time.time() - marker.stat().st_mtime) < NEGATIVE_CACHE_SECONDS


def _touch_negative_cache(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_suffix(path.suffix + '.fail').write_text('', encoding='utf-8')


class GetVoiceSampleView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            voice_id = request.query_params.get('voice')
            try:
                voice = Voice.objects.get(id=voice_id)
            except (Voice.DoesNotExist, ValueError, TypeError):
                return Response({'message': '音色不存在或无权访问'},
                                status=status.HTTP_404_NOT_FOUND)

            text = build_sample_text(voice.name)
            path = sample_cache_path(voice.voice_id, text)
            if not path.exists():
                if _negative_cache_active(path):
                    return Response({'message': '样音暂时无法生成，请稍后再试'},
                                    status=status.HTTP_503_SERVICE_UNAVAILABLE)
                try:
                    audio = synthesize_once(text, voice.voice_id)
                except Exception as e:
                    logger.exception('样音合成失败: voice=%s', voice.id)
                    _touch_negative_cache(path)
                    # UserProfile.id 而非 User.id —— APIUsage.user 是 UserProfile 的 FK
                    record_api_usage(user_id=request.user.userprofile.id, api_type='tts',
                                     model_name=TTS_MODEL, success=False,
                                     error_message=str(e)[:500], update_quota=False)
                    return Response({'message': '样音暂时无法生成，请稍后再试'},
                                    status=status.HTTP_503_SERVICE_UNAVAILABLE)
                _sample_dir().mkdir(parents=True, exist_ok=True)
                path.write_bytes(audio)
                # UserProfile.id 而非 User.id —— APIUsage.user 是 UserProfile 的 FK
                record_api_usage(user_id=request.user.userprofile.id, api_type='tts',
                                 model_name=TTS_MODEL, token_count=len(text),
                                 success=True, update_quota=False)

            return Response({'message': 'success',
                             'url': f'{settings.MEDIA_URL}{SAMPLE_DIR_NAME}/{path.name}'})
        except Exception as e:
            logger.exception('获取样音异常: %s', e)
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

`backend/web/urls.py`：加 import 与路由。

```python
from web.views.create.character.voice.sample import GetVoiceSampleView
```

```python
    path('api/create/character/voice/sample/', GetVoiceSampleView.as_view()),
```

- [ ] **Step 6: 跑测试确认通过**

Run: `... -m pytest web/tests/test_voice_sample.py -v`
Expected: 7 passed（6 条端点用例 + 1 条超时用例）。
`media_root` 是 session 级 autouse fixture（`conftest.py:27`），会把 `MEDIA_ROOT` 指到临时目录；跨用例的缓存残留由 Step 1 里那个清缓存的 autouse fixture 处理，不需要在用例里另做隔离。

- [ ] **Step 7: 提交**

```bash
git add backend/web/utils/tts.py backend/web/views/create/character/voice/sample.py backend/web/urls.py backend/web/tests/test_voice_sample.py backend/web/views/friend/message/chat/chat.py
git commit -m "feat(voice): 音色试听端点 + 一次性 TTS 合成与缓存"
```

---

### Task 5: 前端试听 —— 播放按钮与 `profile` 展示

**Files:**
- Create: `frontend/src/composables/useVoiceSample.js`
- Modify: `frontend/src/views/create/character/components/Voice.vue`
- Test: `frontend/src/composables/__tests__/useVoiceSample.test.js`（新建）
- Test: `frontend/src/views/create/character/components/__tests__/Voice.test.js`（新建）

**Interfaces:**
- Consumes: `GET /api/create/character/voice/sample/?voice=<id>` → `{message, url}`。
- Produces: `useVoiceSample.js` 导出 `playSample(url)`（返回 `HTMLAudioElement`）、`stopCurrentSample()`、`isCurrentSample(el)`；模块级单例，保证同一时刻只有一个试听在播。

- [ ] **Step 1: 写失败测试**

`frontend/src/composables/__tests__/useVoiceSample.test.js`：

```js
// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import { isCurrentSample, playSample, stopCurrentSample } from '@/composables/useVoiceSample.js'

describe('useVoiceSample', () => {
  let created

  beforeEach(() => {
    created = []
    global.Audio = class {
      constructor(src) {
        this.src = src
        this.paused = false
        created.push(this)
      }
      play() { this.paused = false; return Promise.resolve() }
      pause() { this.paused = true }
    }
  })

  it('播新的会先停掉上一个', () => {
    const a = playSample('/a.mp3')
    const b = playSample('/b.mp3')
    expect(a.paused).toBe(true)
    expect(b.paused).toBe(false)
    expect(isCurrentSample(b)).toBe(true)
    expect(isCurrentSample(a)).toBe(false)
  })

  it('stopCurrentSample 停掉当前', () => {
    const a = playSample('/a.mp3')
    stopCurrentSample()
    expect(a.paused).toBe(true)
    expect(isCurrentSample(a)).toBe(false)
  })
})
```

`frontend/src/views/create/character/components/__tests__/Voice.test.js`：

⚠️ **本仓库没有 `@vue/test-utils`**（`package.json` 的 devDependencies 只有 `vitest` / `jsdom` / `vite` 系）。既有前端测试的写法是 `createApp` + `h` + 直接查 DOM（见 `frontend/src/components/character/chat_field/__tests__/VoiceToggle.test.js:1-15`），照抄那个写法，**不要引入新依赖**：

```js
// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick } from 'vue'

vi.mock('@/js/http/api', () => ({ default: { get: vi.fn() } }))
import api from '@/js/http/api'
import Voice from '../Voice.vue'

const VOICES = [
  { id: 1, name: '龙安洋', profile: '阳光大男孩' },
  { id: 2, name: '龙安欢', profile: '欢脱元气女' },
]

function mount(props) {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp({ render: () => h(Voice, props) })
  app.mount(host)
  return host
}

describe('Voice.vue（试听与 profile 展示）', () => {
  beforeEach(() => {
    document.body.innerHTML = ''      // 清掉上个用例挂载的节点
    api.get.mockReset()
    global.Audio = class {
      constructor(src) { this.src = src }
      play() { return Promise.resolve() }
      pause() {}
    }
  })

  it('渲染全部音色名，且只渲染当前音色的 profile', () => {
    const host = mount({ voices: VOICES, curVoice: 2 })
    expect(host.textContent).toContain('龙安洋')
    expect(host.textContent).toContain('龙安欢')
    expect(host.textContent).toContain('欢脱元气女')
    expect(host.textContent).not.toContain('阳光大男孩')
  })

  it('点击试听会请求 sample 接口', async () => {
    api.get.mockResolvedValue({ data: { url: 'https://example.test/media/voice_samples/a.mp3' } })
    const host = mount({ voices: VOICES, curVoice: 1 })
    host.querySelector('[data-test="voice-sample-btn"]').click()
    await nextTick()
    await Promise.resolve()
    expect(api.get).toHaveBeenCalledWith('/api/create/character/voice/sample/',
                                         { params: { voice: 1 } })
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npm run test:unit`
Expected: 新增两个文件的用例 FAIL（模块与按钮都不存在）。

- [ ] **Step 3: 实现 composable**

`frontend/src/composables/useVoiceSample.js`：

```js
// 模块级单例：同一时刻只允许一段试听在播
let current = null

export function stopCurrentSample() {
  if (current) {
    current.pause()
    current = null
  }
}

export function playSample(url) {
  stopCurrentSample()
  const el = new Audio(url)
  current = el
  el.play().catch(() => {})
  return el
}

export function isCurrentSample(el) {
  return current === el
}
```

- [ ] **Step 4: 改 Voice.vue**

```vue
<script setup lang="ts">
import {computed, ref, watch} from "vue";
import api from "@/js/http/api";
import {playSample, stopCurrentSample, isCurrentSample} from "@/composables/useVoiceSample.js";

const props = defineProps(["voices", "curVoice"])
const myVoice = ref(props.curVoice)

watch(() => props.curVoice, newVal => {
  myVoice.value = newVal
})

const curProfile = computed(() => {
  const v = props.voices.find(v => v.id === myVoice.value)
  return v?.profile || ''
})

const loading = ref(false)
const playing = ref(false)
const errorMessage = ref('')
let audioEl = null

async function toggleSample() {
  if (playing.value) {
    stopCurrentSample()
    playing.value = false
    return
  }
  errorMessage.value = ''
  loading.value = true
  try {
    const response = await api.get('/api/create/character/voice/sample/', {
      params: { voice: myVoice.value },
    })
    audioEl = playSample(response.data.url)
    playing.value = true
    audioEl.onended = () => {
      if (isCurrentSample(audioEl)) playing.value = false
    }
    audioEl.onerror = () => {
      playing.value = false
      errorMessage.value = '试听失败，请稍后再试'
    }
  } catch (e) {
    errorMessage.value = '试听失败，请稍后再试'
  } finally {
    loading.value = false
  }
}

defineExpose({
  myVoice
})
</script>

<template>
  <fieldset class="fieldset">
    <legend class="fieldset-legend">音色</legend>
    <div class="flex items-center gap-2">
      <select v-model="myVoice" class="select w-96">
        <option v-for="voice in voices" :key="voice.id" :value="voice.id">
          {{ voice.name }}
        </option>
      </select>
      <button type="button"
              data-test="voice-sample-btn"
              class="btn btn-outline"
              :disabled="loading || !myVoice"
              :title="playing ? '停止试听' : '试听'"
              @click="toggleSample">
        {{ loading ? '加载中' : (playing ? '停止' : '试听') }}
      </button>
    </div>
    <p v-if="curProfile" class="text-sm opacity-70 mt-1">{{ curProfile }}</p>
    <p v-if="errorMessage" class="text-sm text-red-500 mt-1">{{ errorMessage }}</p>
  </fieldset>
</template>
```

（`w-108` 改成 `w-96` 是给试听按钮腾出横向空间；其余样式沿用既有 daisyUI 类。）

- [ ] **Step 5: 跑测试确认通过**

Run: `cd frontend && npm run test:unit`
Expected: 全绿。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/composables/useVoiceSample.js frontend/src/composables/__tests__/useVoiceSample.test.js frontend/src/views/create/character/components/
git commit -m "feat(voice): 音色试听按钮与 profile 展示"
```

---

### Task 6: 全量验证与提 PR（门 3 入口）

- [ ] **Step 1: 后端全量**

Run: `cd backend && D:/MyWork/Miniconda3/envs/py312/python.exe -m pytest web/tests/ -v`
Expected: 全绿；记下实际条数（基线 236 + 本批新增）。

- [ ] **Step 2: 前端全量**

Run: `cd frontend && npm run test:unit`
Expected: 全绿。

- [ ] **Step 3: 前端构建**

Run: `cd frontend && VITE_PLATFORM=docker npm run build`
Expected: 构建成功，产出新的 `index-*.js` hash。
（**必须带 `VITE_PLATFORM=docker`**：默认的 `npm run build` 走的是 `cloud` 模式，AGENTS.md 已标注该模式废弃，产物 hash 与生产不同 —— 生产由 Dockerfile 钉 `VITE_PLATFORM=docker`。不带这个变量的构建只能当"能不能编过"的烟雾测试，不能当"线上同款"。）

- [ ] **Step 4: 分支与 PR**

```bash
git push -u origin feature/gqyin/voice-customization
gh pr create --title "fix(voice): 音色隐患修正 + 命名统一 + 试听" --body-file - <<'EOF'
见 docs/superpowers/specs/2026-09-13-voice-customization-design.md（一期 A+B 批）

- RESTRICT 取代 CASCADE，voice_id 加字符集校验
- 字段名统一为 voice；错误语义 404/400 分档；get_single 判空
- 新增音色试听端点与前端播放按钮
EOF
```

把 PR 链接交给用户走**门 3**（用户人工评审）。门 3 通过前不合并、不部署。

---

## Self-Review

**Spec 覆盖**：
- §1.2 的 8 项问题 → RESTRICT/校验器（Task 1）、404-400 分档与 KeyError（Task 2）、判空（Task 2）、命名（Task 2+3）、`profile` 渲染与试听（Task 5）、重复序列化（Task 2）。
- §5 接口契约 → Task 2（create/update/get_single/get_list）与 Task 4（sample）。
- §6.1 试听流程 → Task 4（步骤 3、5）+ Task 5；§6.1 的"实现方式必须新写"与"记账用 `update_quota=False`"→ Task 4 Step 3/5；负缓存 → Task 4 Step 5 + 测试 B4。
- §9 用例归属：**A1–A4、A7** → Task 2；**A8–A9** → Task 1；**B1–B6** → Task 4（后端 7 条，含超时）与 Task 5（前端 4 条：composable 2 + 组件 2）。**A5、A6、B3 的后半、B7 依赖 C 批字段，随 C 批实现**（见 Global Constraints 的顺序调整）。
- §5 的 `sample_url` 字段**本批不实现**，理由已写在 Global Constraints。

**Type 一致性**：`serialize_voice` 在 Task 2 定义、在 `get_list.py` 与 `get_single.py` 使用；`synthesize_once(text, voice_id) -> bytes` 在 Task 4 Step 3 定义、Step 5 使用、测试以 `web.views.create.character.voice.sample.synthesize_once` 为 patch 目标（即"使用处"）；`playSample(url) / stopCurrentSample() / isCurrentSample(el)` 在 Task 5 Step 3 定义、Step 4 使用、测试同步。

**未决/转 C 批**：`owner` / `visibility` / `status` 三字段、列表过滤与 `is_mine`、B7 的禁用逻辑、数据迁移 0024。C 批的计划**等 A+B 落地后再写** —— 因为 A+B 正好重构了 C 要改的那几个文件（`get_list.py` / `get_single.py` / `serializer.py`），现在写会与落地后的真实代码漂移。

**后续批次必须沿用的一条守卫**：任何调用 `record_api_usage` 的新端点（C 批的 remove、D 批的 clone 都会调用），其用例都要照 `test_asr.py:106` 的做法**强制 `User.id != UserProfile.id`** 之后再断言 `user_id`。默认夹具下两个 id 可能恰好相等，此时 `user_id == user_profile.id` 这类断言即使代码误传 `User.id` 也照样通过 —— 这是这条守卫唯一有区分力的前提。

**写计划时实测到、会直接决定写法不写错的三个事实**：

1. **`settings.MEDIA_URL` 是绝对地址，不是 `/media/`**：`settings.py:168-170` 的默认值按 DEBUG 分支（`http://127.0.0.1:8000/media/` / `https://115.190.245.146/media/`），而线上靠 `DJANGO_MEDIA_URL` 覆盖 —— 实测服务器容器内的值是 `https://8.153.201.12/media/`。所以样音 URL 必须用 `settings.MEDIA_URL` 拼接（天然跨环境正确），测试断言也要用 `settings.MEDIA_URL` 而不是硬写 `/media/`。顺带核实：默认值里那个 `115.190.245.146` 是已废弃的旧服务器地址，实测 `curl` 返回 `000`（不通）；线上没出问题只是因为 `DJANGO_MEDIA_URL` 设对了。
2. **`media_root` 是 session 级 autouse 夹具**（`conftest.py:27`），而 `voice` 夹具的 `voice_id` 固定为 `test_voice_001`（`conftest.py:85`）—— 缓存键因此跨用例固定，样音会残留导致"第二次请求"类用例误判。Task 4 的测试文件里必须有那个清缓存的 autouse 夹具。
3. **仓库没有 `@vue/test-utils`**：前端既有测试用手工 `createApp` + `h` + 查 DOM（`VoiceToggle.test.js:1-15`），Task 5 的组件测试照抄该写法，不引入新依赖。
