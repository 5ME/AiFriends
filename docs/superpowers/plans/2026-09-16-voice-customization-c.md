# 音色自定义（一期 · C 批：归属模型）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `Voice` 加上归属与可见性（`owner` / `visibility` / `status`），让"我的音色"与"平台音色"在接口和界面上分开，并把 A+B 批因缺这两个字段而推迟的 4 条验收项补齐。

**Architecture:** 迁移 `0024` 一次加三个字段（字段一次立好，二期加公开共享时不再改表），**并带一个数据迁移把存量音色全部置为 `public`**，否则默认值会让线上现有的「观音菩萨」从所有人的选择列表里消失。可见性规则收敛成一个 `Q` 对象，被列表、详情、选角校验、试听校验四处共用，杜绝"改一处漏一处"。前端用原生 `<optgroup>` 分组，非 `ready` 音色禁用试听。

**Tech Stack:** Django 6.0.2 / DRF / pytest + pytest-django / Vue 3 + Vitest

**Spec:** `docs/superpowers/specs/2026-09-13-voice-customization-design.md`（§4.2 字段、§5 接口、§6.1 试听、§9 C 批、§10 C 批验收、§11 风险）

## Global Constraints

- **分支**：`feature/gqyin/voice-ownership`。不在 master 上提交。
- **状态码口径**（spec §5，A+B 已落地）：**404** = 这个音色对你来说不存在（不存在、**他人的私有音色**，两者 message 必须**逐字相同**）；**400** = 可见但当下不能用（`status != 'ready'`、参数不合法、配额）；**503** = 上游不可用或超时。
- **迁移**：`0024`，三个 `AddField` + **一个 `RunPython` 数据迁移**（存量置 public）。
- **异常**：不裸 `except`；一律 `except Exception as e:` + `logger.exception(...)`。
- **不新增依赖**、**不改 `requirements.txt`**、**不做公开共享的界面**（那是二期）。
- **后端测试**：`cd backend && D:/MyWork/Miniconda3/envs/py312/python.exe -m pytest web/tests/ -v`
  基线 **258 passed, 3 deselected**（A+B 合并后的实测值）。
- **前端测试**：`cd frontend && npm run test:unit`，基线 **154 passed (19 files)**。

### 本批的爆炸半径（动手前必须知道）

`conftest.py:85` 的 `voice` 夹具是 `baker.make(Voice, name="Test Voice", voice_id="test_voice_001")` —— 只给了 `name` 和 `voice_id`。加上新字段后：

- `owner` 会是 `None`（model_bakery 对可空外键在未开 `fill_optional` 时直接跳过）→ 平台音色，与预期一致；
- **但 `visibility` 和 `status` 都是 `choices` 字段，而 model_bakery 对 choices 字段是随机取一个选项**（`model_bakery/baker.py:829-831` → `random_gen.gen_from_choices`）：`visibility` 50/50，`status` 各 1/3。

所以后果不是"集体红"，而是**随机红**：两种随机都 favorable 时（约 1/6 概率）整轮全绿，实施者会误判成"加了字段没影响"。更要紧的是**只钉 `visibility` 不够** —— `status` 若仍随机，C 批新加的 `status != 'ready' → 400` 闸门会让 create / update / sample 三条路径在**约 2/3 的轮次里红**，而且这个 flakiness 在这批做完之后、CI 里会一直存在。**所以夹具必须把两个字段都钉死。**

受影响的是 **3 个**测试文件（`test_character.py` / `test_voice_integrity.py` / `test_voice_sample.py`）。`test_homepage.py` 虽然也用了这个夹具，但它的用例只打 `/api/homepage/index/`，一条都不走音色端点，没有可见性/可用性闸门，全程是绿的。

另有一条 pin 用例要跟着契约走：`test_voice_integrity.py` 的 `test_voice_list_shape` 断言 `set(first) == {'id','name','profile'}`。C 批给序列化加了 `status`/`is_mine`（3 + 2 = 5 个键），该断言要更新 —— **但必须放在 Task 2**，因为序列化是在那一步才改的；放进 Task 1 会让那一步的"全绿"根本不可能达成。

---

### Task 0: 建分支并提交本计划

**Files:**
- Add: `docs/superpowers/plans/2026-09-16-voice-customization-c.md`（已在工作区，untracked）

- [ ] **Step 1: 建分支**

```bash
git checkout -b feature/gqyin/voice-ownership
```

- [ ] **Step 2: 提交本计划**

```bash
git add docs/superpowers/plans/2026-09-16-voice-customization-c.md
git commit -m "docs(voice): C 批（归属模型）实施计划"
```

（spec 已在 PR #45 入库，本次只带这一份计划。）

---

### Task 1: 模型三字段 + 迁移 0024（含数据迁移）+ 夹具修正

**Files:**
- Modify: `backend/web/models/character.py`
- Create: `backend/web/migrations/0024_*.py`（`makemigrations` 生成后手工插入 `RunPython`）
- Modify: `backend/web/tests/conftest.py`（`voice` 夹具）
- Test: `backend/web/tests/test_voice_ownership.py`（新建）

**Interfaces:**
- Produces: `Voice.owner`（FK→UserProfile，可空）、`Voice.visibility`（`private`/`public`，默认 `private`）、`Voice.status`（`ready`/`deploying`/`rejected`，默认 `ready`）。

- [ ] **Step 1: 写失败测试**

新建 `backend/web/tests/test_voice_ownership.py`：

```python
import importlib

from django.contrib.auth.models import User

from web.models.character import Voice
from web.models.user import UserProfile


class TestFields:
    def test_fixture_shape(self, voice):
        """钉住夹具的形状 —— 谁把这三个显式值去掉，就会把 choices 随机性放回来"""
        assert voice.visibility == 'public'
        assert voice.status == 'ready'
        assert voice.owner is None          # 夹具不设 owner → 平台音色

    def test_field_defaults(self):
        """字段默认值 —— 这是 0024 数据迁移存在的**唯一理由**，必须钉住。

        `visibility` 默认 `private`：若有人把默认值改成 `public`，"存量置 public"那步
        就变成空操作，而 spec §4.2 与风险说明会一起失真。夹具显式传了值，
        所以默认值不会被任何其它用例覆盖到，只能在这里守。
        """
        assert Voice._meta.get_field('visibility').default == 'private'
        assert Voice._meta.get_field('status').default == 'ready'

    def test_owner_can_be_set(self, voice, user_profile):
        voice.owner = user_profile
        voice.visibility = 'private'
        voice.save()
        voice.refresh_from_db()
        assert voice.owner_id == user_profile.id

    def test_deleting_owner_deletes_voice(self, user_profile):
        """owner 是 CASCADE：用户注销时其音色随之清理（与 Character.author 一致）"""
        v = Voice.objects.create(name='v', voice_id='v_1', owner=user_profile)
        user_profile.user.delete()
        assert not Voice.objects.filter(id=v.id).exists()


class TestDataMigration:
    """C4：0024 的数据迁移必须把存量音色置为 public，否则默认值会让它们从列表里消失"""

    def test_marks_existing_rows_public(self, voice):
        from web.models.character import Voice as RealVoice

        mod = importlib.import_module(
            'web.migrations.0024_voice_ownership_visibility_status')

        class _FakeApps:
            def get_model(self, app_label, model_name):
                return RealVoice

        RealVoice.objects.filter(pk=voice.pk).update(visibility='private')
        mod.mark_existing_public(_FakeApps(), None)
        voice.refresh_from_db()
        assert voice.visibility == 'public'
```

（迁移文件名以 `makemigrations` 实际生成的为准，Step 4 之后回来对齐这一行。）

- [ ] **Step 2: 跑测试确认失败**

Run: `... -m pytest web/tests/test_voice_ownership.py -v`
Expected: `TestFields` **四条**全 FAIL（字段不存在 → `AttributeError`；`test_field_defaults` 会在 `get_field('visibility')` 抛 `FieldDoesNotExist`）；`TestDataMigration` FAIL（模块不存在 → `ModuleNotFoundError`）。

- [ ] **Step 3: 改模型**

`backend/web/models/character.py` 的 `Voice`：

```python
    owner = models.ForeignKey(UserProfile, null=True, blank=True,
                              on_delete=models.CASCADE)
    visibility = models.CharField(max_length=10, default='private',
                                  choices=[('private', '私有'), ('public', '公开')])
    status = models.CharField(max_length=12, default='ready', choices=[
        ('ready', '可用'), ('deploying', '审核中'), ('rejected', '审核未通过'),
    ])
```

放在 `is_builtin` 之后、`created_at` 之前。（`UserProfile` 在该文件已导入，不用字符串引用。）

- [ ] **Step 4: 生成迁移并手工插入数据迁移**

Run: `cd backend && D:/MyWork/Miniconda3/envs/py312/python.exe manage.py makemigrations web`
Expected: 生成 `0024_*.py`，含三个 `AddField`、**无 `RunPython`**。

然后**手工**编辑该文件，在 `operations` 末尾追加数据迁移（并新增顶层函数）：

```python
def mark_existing_public(apps, schema_editor):
    """存量音色全部置为 public：它们此前对所有用户可见，默认值 private 会造成可见性回归
    （线上「观音菩萨」会从选择列表消失）。反向操作留 noop —— 回滚只需保留可见性。"""
    Voice = apps.get_model('web', 'Voice')
    Voice.objects.update(visibility='public')


class Migration(migrations.Migration):
    # ...
    operations = [
        # ...三个 AddField...
        migrations.RunPython(mark_existing_public, migrations.RunPython.noop),
    ]
```

- [ ] **Step 5: 修夹具（两个字段都要钉死）**

`backend/web/tests/conftest.py` 的 `voice` 夹具改成：

```python
@pytest.fixture
def voice(db):
    """测试音色：显式钉死 visibility/status —— model_bakery 对 choices 字段是随机取值的"""
    return baker.make(Voice, name="Test Voice", voice_id="test_voice_001",
                      visibility='public', status='ready', owner=None)
```

**这一步不要动 `test_voice_list_shape`** —— 那条 pin 用例的键集合要等 Task 2 改完序列化之后再改（见 Task 2 Step 4）。

- [ ] **Step 6: 跑测试确认通过**

Run: `... -m pytest web/tests/ -v`
Expected: 全绿（258 + 本批新增）。若有红，优先看是不是夹具漏改。

- [ ] **Step 7: 提交**

```bash
git add backend/web/models/character.py backend/web/migrations/0024_*.py \
        backend/web/tests/conftest.py \
        backend/web/tests/test_voice_ownership.py
git commit -m "feat(voice): Voice 加归属/可见性/状态三字段，存量置 public（迁移 0024）"
```

---

### Task 2: 可见性规则收敛一处 + 序列化 + 列表/详情

**Files:**
- Create: `backend/web/views/create/character/voice/visibility.py`
- Modify: `backend/web/views/create/character/voice/serializer.py`
- Modify: `backend/web/views/create/character/voice/get_list.py`
- Modify: `backend/web/views/create/character/get_single.py`
- Modify: `backend/web/tests/test_voice_integrity.py`（`test_voice_list_shape` 的键集合 —— 从 Task 1 挪过来，必须与序列化改动**同一次提交**，否则本地绿、CI 红）
- Test: `backend/web/tests/test_voice_ownership.py`（追加）

**Interfaces:**
- Produces: `visibility_q(profile) -> Q`、`visible_voices(profile) -> QuerySet`、`is_voice_visible(voice, profile) -> bool`
- Produces: `serialize_voice(voice, profile) -> dict`，键为 `id` / `name` / `profile` / `status` / `is_mine`

- [ ] **Step 1: 写失败测试**

追加到 `test_voice_ownership.py`：

```python
class TestVisibilityRule:
    """C1 / C3：列表只回公开或自己的，且 is_mine 正确"""

    def _make(self, user_profile, voice_id, **kw):
        return Voice.objects.create(name=voice_id, voice_id=voice_id,
                                    owner=user_profile, **kw)

    def test_list_returns_public_and_own_only(self, auth_client, user_profile,
                                             other_user, voice):
        mine = self._make(user_profile, 'mine_1', visibility='private')
        # other_user 夹具自身就创建了 UserProfile（conftest.py:113-118）
        public = self._make(other_user.userprofile, 'publ_1', visibility='public')
        others_private = Voice.objects.create(
            name='op', voice_id='op_1',
            owner=UserProfile.objects.create(user=User.objects.create_user('third')),
            visibility='private')

        resp = auth_client.get('/api/create/character/voice/get_list/')
        ids = {v['id'] for v in resp.json()['voices']}
        assert voice.id in ids            # 夹具是 public
        assert mine.id in ids             # 自己的私有音色可见
        assert public.id in ids           # 别人的公开音色可见
        assert others_private.id not in ids   # 别人的私有音色不可见

    def test_is_mine_flag(self, auth_client, user_profile, voice):
        mine = self._make(user_profile, 'mine_2', visibility='private')
        resp = auth_client.get('/api/create/character/voice/get_list/')
        by_id = {v['id']: v for v in resp.json()['voices']}
        assert by_id[mine.id]['is_mine'] is True
        assert by_id[voice.id]['is_mine'] is False      # 平台音色

    def test_status_exposed(self, auth_client, user_profile, voice):
        rejected = self._make(user_profile, 'rej_1', status='rejected')
        resp = auth_client.get('/api/create/character/voice/get_list/')
        by_id = {v['id']: v for v in resp.json()['voices']}
        assert by_id[rejected.id]['status'] == 'rejected'

    def test_get_single_voices_filtered(self, auth_client, character, voice):
        """详情页的音色下拉也走同一条可见性规则"""
        Voice.objects.create(name='op2', voice_id='op_2',
                             owner=UserProfile.objects.create(
                                 user=User.objects.create_user('fourth')),
                             visibility='private')
        resp = auth_client.get('/api/create/character/get_single/',
                               {'character_id': character.id})
        names = {v['name'] for v in resp.json()['voices']}
        assert 'op2' not in names
```

- [ ] **Step 2: 跑测试确认失败**

Run: `... -m pytest web/tests/test_voice_ownership.py -v -k TestVisibilityRule`
Expected: 全部 FAIL（列表当前无过滤、无 `is_mine`/`status` 键 → `KeyError`）。

- [ ] **Step 3: 新建可见性模块**

`backend/web/views/create/character/voice/visibility.py`：

```python
"""音色可见性规则 —— 只在这里定义一次。

列表（get_list）、详情（get_single）、选角（create/update）、试听（sample）
四处共用同一个 Q，避免"改了列表忘了校验"这类漏洞。
"""
from django.db.models import Q

from web.models.character import Voice


def visibility_q(profile):
    return Q(visibility='public') | Q(owner=profile)


def visible_voices(profile):
    return Voice.objects.filter(visibility_q(profile)).order_by('id')


def is_voice_visible(voice, profile):
    return Voice.objects.filter(visibility_q(profile), pk=voice.pk).exists()
```

- [ ] **Step 4: 改序列化与两处调用**

`voice/serializer.py`：

```python
def serialize_voice(voice, profile):
    """音色对外表示。get_list / get_single 共用一份，避免改一处漏一处。"""
    return {
        'id': voice.id,
        'name': voice.name,
        'profile': voice.profile,
        'status': voice.status,
        'is_mine': voice.owner_id is not None and voice.owner_id == profile.id,
    }
```

`voice/get_list.py`：

```python
from web.views.create.character.voice.serializer import serialize_voice
from web.views.create.character.voice.visibility import visible_voices
...
            profile = request.user.userprofile
            voices = [serialize_voice(v, profile) for v in visible_voices(profile)]
```

`get_single.py` 同样改为按当前用户的 profile 过滤并传进 `serialize_voice`。

**同时**把 `test_voice_integrity.py` 的 pin 用例 `test_voice_list_shape` 更新到新契约（5 个键）：

```python
        assert set(first) == {'id', 'name', 'profile', 'status', 'is_mine'}
```

- [ ] **Step 5: 跑测试确认通过**

Run: `... -m pytest web/tests/test_voice_ownership.py -v` → 全绿；再跑 `... -m pytest web/tests/ -q` 确认无回归。

- [ ] **Step 6: 提交**

```bash
git add backend/web/views/create/character/ backend/web/tests/test_voice_ownership.py \
        backend/web/tests/test_voice_integrity.py
git commit -m "feat(voice): 可见性规则收敛一处，列表/详情按归属过滤"
```

---

### Task 3: 三处校验 —— 选角、改角、试听（补齐 A5 / A6 / B3 后半）

**Files:**
- Modify: `backend/web/views/create/character/create.py`
- Modify: `backend/web/views/create/character/update.py`
- Modify: `backend/web/views/create/character/voice/sample.py`
- Test: `backend/web/tests/test_voice_ownership.py`（追加）

**Interfaces:**
- Consumes: Task 2 的 `is_voice_visible(voice, profile)`。

- [ ] **Step 1: 写失败测试**

追加。**顶部要补助手**：`BytesIO` / `PIL.Image` / `SimpleUploadedFile` / `rest_framework.status` / `unittest.mock.patch` 的 import，以及 `_make_test_image`（从 `test_voice_integrity.py` 复制 —— 本仓库已有两处副本，跟随既有做法）。

```python
def _make_test_image(name="test.jpg"):
    """创建 1x1 白色 JPEG 的内存文件（与 test_character.py / test_voice_integrity.py 同一写法）"""
    img = Image.new("RGB", (1, 1), color="white")
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/jpeg")


class TestSelectionGuards:
    """A5 / A6 / B3 后半：选角与试听都要过可见性与可用性两道闸"""

    def _other_private(self):
        other = UserProfile.objects.create(user=User.objects.create_user('other2'))
        return Voice.objects.create(name='私有', voice_id='priv_1',
                                    owner=other, visibility='private')

    def _payload(self, voice_value):
        """create 的完整必填载荷。校验顺序是 name→introduction→system_prompt→
        photo→background_image→voice（`create.py:27-45`），只传 voice 会先栽在 name 上返回 400。"""
        return {
            'name': 'n', 'introduction': 'i', 'system_prompt': 's',
            'voice': voice_value,
            'photo': _make_test_image('photo.jpg'),
            'background_image': _make_test_image('bg.jpg'),
        }

    def test_create_with_others_private_voice_returns_404(self, auth_client):
        """A6：404，且 message 与"不存在"逐字相同（否则 404 成了存在性探测器）

        ⚠️ 必须传齐必填字段：只传 {'voice': ...} 的话两次都会拿到 400「角色名称不能为空」，
        那个"message 逐字相同"的断言就变成在两个 400 之间比较，等于什么都没验证。
        """
        v = self._other_private()
        r1 = auth_client.post('/api/create/character/create/', self._payload(v.id))
        r2 = auth_client.post('/api/create/character/create/', self._payload(999999))
        assert r1.status_code == status.HTTP_404_NOT_FOUND
        assert r2.status_code == status.HTTP_404_NOT_FOUND
        assert r1.json()['message'] == r2.json()['message']

    def test_update_with_others_private_voice_returns_404(self, auth_client, character):
        v = self._other_private()
        resp = auth_client.post('/api/create/character/update/', {
            'character_id': character.id, 'name': 'n', 'introduction': 'i',
            'system_prompt': 's', 'voice': v.id})
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_update_with_not_ready_voice_returns_400(self, auth_client, character,
                                                     voice):
        """A5：可见但没就绪 → 400（与 404 区分开，用户能知道该等还是该换）"""
        voice.status = 'deploying'
        voice.save(update_fields=['status'])
        resp = auth_client.post('/api/create/character/update/', {
            'character_id': character.id, 'name': 'n', 'introduction': 'i',
            'system_prompt': 's', 'voice': voice.id})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_sample_of_others_private_voice_returns_404(self, auth_client):
        v = self._other_private()
        resp = auth_client.get('/api/create/character/voice/sample/', {'voice': v.id})
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_sample_of_not_ready_voice_returns_400(self, auth_client, voice):
        """B3 后半：没就绪就不该去打阿里云（用 mock 断言零调用）"""
        voice.status = 'rejected'
        voice.save(update_fields=['status'])
        with patch('web.views.create.character.voice.sample.synthesize_once') as m:
            resp = auth_client.get('/api/create/character/voice/sample/',
                                   {'voice': voice.id})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert m.call_count == 0
```

（顶部所需的 import 见本节开头那句，不再重复。）

- [ ] **Step 2: 跑测试确认失败**

Run: `... -m pytest web/tests/test_voice_ownership.py -v -k TestSelectionGuards`
Expected: 前两条 FAIL（当前对他人私有音色会拿到 200/400 而非 404）、后三条 FAIL（当前不查 `status`、试听会对非 ready 音色真的去打阿里云）。

- [ ] **Step 3: 改三处**

`create.py` / `update.py`：在既有的 `Voice.objects.get(id=voice_pk)` 之后、赋值之前插入：

```python
            if not is_voice_visible(voice, user_profile):
                # message 必须与"不存在"逐字相同 —— 否则 404 变成存在性探测器
                return Response({'message': '音色不存在或无权访问'},
                                status=status.HTTP_404_NOT_FOUND)
            if voice.status != 'ready':
                # 措辞与 spec §5/§7 一致：可见但没就绪 → 400（与 404 区分开，用户能知道该等还是该换）
                return Response({'message': '该音色尚不可用（审核中 / 审核未通过）'},
                                status=status.HTTP_400_BAD_REQUEST)
```

（`create.py` 已有 `user_profile` 变量；`update.py` 需用 `request.user.userprofile`。）

`voice/sample.py`：在 `Voice.objects.get` 之后、`build_sample_text` 之前插入同样两道闸（可见性 → 404；`status != 'ready'` → 400 且**不调用** `synthesize_once`）。

- [ ] **Step 4: 跑测试确认通过**

Run: `... -m pytest web/tests/ -q` → 全绿。

- [ ] **Step 5: 提交**

```bash
git add backend/web/views/create/character/ backend/web/tests/test_voice_ownership.py
git commit -m "feat(voice): 选角与试听补可见性/可用性校验（补齐 A5/A6/B3 后半）"
```

---

### Task 4: `seed_builtins` 写 visibility（C5）

**Files:**
- Modify: `backend/web/management/commands/seed_builtins.py`
- Test: `backend/web/tests/test_seed_builtins.py`

**Interfaces:**
- 内置音色被 seed 后 `visibility='public'`；已存在但 `visibility` 不对的行会被纠正。

- [ ] **Step 1: 改失败测试**

`test_seed_builtins.py` 里加一条（该文件顶部已 `from django.core.management import call_command`，**`call_command` 是函数不是夹具**，夹具用 `db`）：

```python
    def test_builtin_voices_are_public(self, db):
        call_command('seed_builtins')
        assert all(v.visibility == 'public'
                   for v in Voice.objects.filter(is_builtin=True))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `... -m pytest web/tests/test_seed_builtins.py -v` → 新用例 FAIL（seed 不设 visibility → 默认 private）。

- [ ] **Step 3: 改 seed 命令**

`_seed_voices()` 里：创建时带上 `visibility='public'`；更新分支把 `visibility` 也纳入"是否需要更新"的比较与 `update_fields`：

```python
            if voice is None:
                Voice.objects.create(**spec, is_builtin=True, visibility='public')
                ...
            changed = (
                voice.name != spec['name']
                or voice.profile != spec['profile']
                or not voice.is_builtin
                or voice.visibility != 'public'
            )
            if changed:
                ...
                voice.visibility = 'public'
                voice.save(update_fields=['name', 'profile', 'is_builtin', 'visibility'])
```

- [ ] **Step 4: 跑测试确认通过**

Run: `... -m pytest web/tests/test_seed_builtins.py -v` → 全绿。

- [ ] **Step 5: 提交**

```bash
git add backend/web/management/commands/seed_builtins.py backend/web/tests/test_seed_builtins.py
git commit -m "feat(voice): seed_builtins 把内置音色置为 public"
```

---

### Task 5: 前端 —— 分组标识 + 非 ready 禁用试听（C7）

**Files:**
- Modify: `frontend/src/views/create/character/components/Voice.vue`
- Test: `frontend/src/views/create/character/components/__tests__/Voice.test.js`

**Interfaces:**
- Consumes: 列表接口新增的 `status` / `is_mine`。

- [ ] **Step 1: 写失败测试**

在 `Voice.test.js` 里补两条，并把 `VOICES` 扩成带 `status`/`is_mine` 的形态：

```js
const VOICES = [
  { id: 1, name: '龙安洋', profile: '阳光大男孩', is_mine: false, status: 'ready' },
  { id: 2, name: '龙安欢', profile: '欢脱元气女', is_mine: false, status: 'ready' },
  { id: 3, name: '我的音色', profile: '审核中的', is_mine: true, status: 'deploying' },
]
```

```js
  it('按归属分成「我的音色」与「平台音色」两组', () => {
    const host = mount({ voices: VOICES, curVoice: 1 })
    const labels = [...host.querySelectorAll('optgroup')].map(g => g.getAttribute('label'))
    expect(labels).toEqual(['我的音色', '平台音色'])
    expect(host.querySelector('optgroup[label="我的音色"]').textContent).toContain('我的音色')
  })

  it('非 ready 音色的试听按钮禁用，且点击不发请求', async () => {
    const host = mount({ voices: VOICES, curVoice: 3 })
    const btn = host.querySelector('[data-test="voice-sample-btn"]')
    expect(btn.disabled).toBe(true)
    btn.click()
    await nextTick()
    expect(api.get).not.toHaveBeenCalled()
  })
```

（既有 3 条用例的 `VOICES` 断言要跟着新形态走 —— 「只渲染当前音色的 profile」那条仍然成立。）

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npm run test:unit -- src/views/create/character/components/__tests__/Voice.test.js`
Expected: 新增两条 FAIL（没有 `optgroup`、按钮未按 status 禁用）。

- [ ] **Step 3: 改 `Voice.vue`**

```js
const mineVoices = computed(() => props.voices.filter(v => v.is_mine))
const platformVoices = computed(() => props.voices.filter(v => !v.is_mine))

const STATUS_LABEL = { deploying: '审核中', rejected: '审核未通过' }

// 注意别叫 curVoice —— prop 已经叫 curVoice 了，同名两种含义（prop 是"父组件传进来的当前值"，
// 这里算的是"按 myVoice 选中的那个对象"），改名避免读代码时混淆。
const selectedVoice = computed(() => props.voices.find(v => v.id === myVoice.value))
const curProfile = computed(() => selectedVoice.value?.profile || '')
const curReady = computed(() => !selectedVoice.value || selectedVoice.value.status === 'ready')
```

模板把 `<select>` 的内容换成两组（空组不渲染）：

```html
      <select v-model="myVoice" class="select w-96">
        <optgroup v-if="mineVoices.length" label="我的音色">
          <option v-for="v in mineVoices" :key="v.id" :value="v.id">
            {{ v.name }}{{ STATUS_LABEL[v.status] ? '（' + STATUS_LABEL[v.status] + '）' : '' }}
          </option>
        </optgroup>
        <optgroup label="平台音色">
          <option v-for="v in platformVoices" :key="v.id" :value="v.id">
            {{ v.name }}
          </option>
        </optgroup>
      </select>
```

试听按钮加 `!curReady` 禁用，并在下方给一句提示：

```html
      <button type="button" data-test="voice-sample-btn" class="btn btn-outline"
              :disabled="loading || !myVoice || !curReady"
              :title="curReady ? (playing ? '停止试听' : '试听') : '该音色尚不可用'"
              @click="toggleSample">
```

```html
    <p v-if="!curReady" class="text-sm opacity-70 mt-1">该音色尚不可用，暂时无法试听</p>
```

**不要**在 `toggleSample` 里再加 `if (!curReady) return` 这类守卫：已实测 jsdom 对 `disabled` 按钮**不派发 click**（`node -e` 探针返回 `false`），所以「点击不发请求」那半条断言靠 `disabled` 就成立；多加一层守卫只是冗余代码。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && npm run test:unit` → 全绿（154 + 新增）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/create/character/components/
git commit -m "feat(voice): 音色按归属分组，非就绪音色禁用试听"
```

---

### Task 6: 全量验证与提 PR（门 3 入口）

- [ ] **Step 1: 后端全量**

Run: `cd backend && D:/MyWork/Miniconda3/envs/py312/python.exe -m pytest web/tests/ -v`
Expected: 全绿；记下实际条数（基线 258 + 本批新增）。

- [ ] **Step 2: 前端全量**

Run: `cd frontend && npm run test:unit` → 全绿。

- [ ] **Step 3: 生产同款构建**

Run: `cd frontend && VITE_PLATFORM=docker npm run build`
Expected: 构建成功，产出新的 `index-*.js`。

- [ ] **Step 4: 分支与 PR**

```bash
git push -u origin feature/gqyin/voice-ownership
gh pr create --title "feat(voice): 归属模型 —— 我的音色与平台音色" --body-file - <<'EOF'
音色自定义一期 · **C 批**（spec: `docs/superpowers/specs/2026-09-13-voice-customization-design.md`）

## 做了什么

- 迁移 `0024`：`Voice` 加 `owner` / `visibility` / `status` 三字段（字段一次立好，二期加公开共享不再改表），**并带数据迁移把存量音色置为 `public`** —— 否则默认值会让线上「观音菩萨」从所有人的选择列表里消失
- 可见性规则收敛到一处（`voice/visibility.py` 的 `visibility_q`），列表 / 详情 / 选角 / 试听四处共用，杜绝"改了列表忘了校验"
- 列表与详情按归属过滤，并新增 `status` / `is_mine` 两个字段
- `seed_builtins` 把内置音色置为 `public`（幂等，已存在但不对的行会被纠正）
- 前端：音色下拉按归属分成「我的音色」/「平台音色」两组（原生 `optgroup`），非 ready 音色禁用试听

## 本批补齐的四条推迟验收项（A+B 时勾不了的那四条）

| 项 | 结果 |
|---|---|
| 可见但 `status != 'ready'` → 400 | create / update 均校验 |
| 他人的私有音色 → 404 且 message 与"不存在"**逐字相同** | 有专门断言，防止 404 变成存在性探测器 |
| 非 ready 音色的试听 → 400 且**不打阿里云** | 用 mock 断言零调用 |
| 非 ready 音色的播放按钮禁用 | Vitest 断言 `disabled` 且点击不发请求 |

## 证据

- 后端：`pytest web/tests/ -v` → 具体条数见评论区（基线 258）
- 前端：`npm run test:unit` → 具体条数见评论区（基线 154）
- 构建：`VITE_PLATFORM=docker npm run build`
- 迁移：`0024`，三个 `AddField` + 一个 `RunPython`

## 部署与验收（门 4）

- 部署：WSL `ACR_IMAGE=<ACR 公网域名>:voice-c-1 ./deploy/build.sh` → 服务器换 tag 部署
- ⚠️ **重点看可见性回归**：线上 3 个音色（龙安洋 / 龙安欢 / 观音菩萨）**必须全部仍然出现在创建角色页的下拉框里**，一个都不能少 —— 这是数据迁移唯一的验收点
- 创建角色页的下拉框应分成「我的音色」/「平台音色」两组；现在没有用户自建音色，所以「我的音色」组应为空（不渲染）
EOF
```

把 PR 链接交给用户走**门 3**。门 3 通过前不合并、不部署。

---

## Self-Review

**Spec 覆盖**
- §4.2 三字段与语义 → Task 1；数据迁移（存量置 public）→ Task 1。**本批不新增 `target_model`**（spec 决定，风险 5 已登记）。
- §5 接口：`get_list`/`get_single` 加 `status`/`is_mine` 并按可见性过滤 → Task 2；`create`/`update` 的 404/400 → Task 3；`sample` 的 404/400 → Task 3。
- §9 C 批：C1/C3 → Task 2；C2/C6 → Task 3；C4 → Task 1；C5 → Task 4；C7 → Task 5。
- **本批补齐的四条推迟项**：A5（非 ready → 400）→ Task 3；A6（他人私有 → 404 且 message 逐字相同）→ Task 3；B3 后半（试听非 ready → 400 且不打阿里云）→ Task 3；B7（非 ready 禁用播放按钮）→ Task 5。
- §6.1 的可见性一条（"不可见 → 404"）→ Task 3。

**Type 一致性**：`visibility_q` / `visible_voices` / `is_voice_visible` 在 Task 2 定义、Task 3 使用；`serialize_voice(voice, profile)` 的签名在 Task 2 定义并被 `get_list` / `get_single` 调用（**A+B 里它是单参数，C 批改成双参数**，两个调用点都在 Task 2 内改完）；前端 `STATUS_LABEL` / `curReady` 在 Task 5 内自洽。

**未决/转 D 批**：复刻接线（`clone` 端点、OSS、Celery Beat 状态刷新、配额）、`clean_dirty_characters` 的 DEBUG 闸、删除音色时同步删阿里云侧。D 批计划等 OSS 凭据备妥后再写 —— 现在写会与 D 批前置条件（bucket/AccessKey 尚不存在）脱节。
