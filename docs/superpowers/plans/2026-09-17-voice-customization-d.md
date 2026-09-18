# 音色自定义（一期 · D 批：复刻接线）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户上传样本复刻出自己的私有音色、用在自己的角色上，并把删除路径同步到阿里云侧。

**Architecture:** 样本上传到 OSS（**对象级 `acl='private'`** —— 桶本身是 `public-read`）→ 生成 5 分钟有效的**签名 URL** 交给阿里云 `voice-enrollment` 的 `create_voice` → 拿到 `voice_id` 后建 `Voice(status='deploying')` → **无论成败立即删除 OSS 对象** → 由 **Celery Beat** 每 5 分钟扫一批 `deploying` 行、用 `query_voice` 回写状态（`OK → ready`、`UNDEPLOYED → rejected`）。删除音色时**先调阿里云 `delete_voice`，成功才删本地行**。

**Tech Stack:** Django 6.0.2 / DRF / `alibabacloud-oss-v2==1.2.5`（**已在 requirements**）/ DashScope `voice-enrollment` + `cosyvoice-v3-flash` / Celery Beat / Vue 3 + Vitest

**Spec:** `docs/superpowers/specs/2026-09-13-voice-customization-design.md`（§4.2 状态字段、§5 接口、§6.2 复刻与删除、§7 错误表、§9 D 批、§10 D 批验收、§11 风险 5/9/10/12/14）

## Global Constraints

- **分支**：`feature/gqyin/voice-clone`。不在 master 上提交。
- **状态码口径**（spec §5）：**404** = 这个音色对你来说不存在；**400** = 可见但当下不能用（非 ready、参数不合法、配额、被角色引用）；**503** = 上游不可用或超时。⚠️ **两种 404 的 message 必须逐字相同**（create / update / sample 已有此约定，本批的 clone / remove 沿用 `音色不存在或无权访问`）。
- **样本存储**：桶 `gqyin-ai-friends` 实测是 `public-read`，**上传必须带对象级 `acl='private'`**，并只用签名 URL（5 分钟有效）交给阿里云。
- **超时**：请求路径上的阻塞调用一律 **5 秒**（OSS 上传、`create_voice`、`delete_voice`）；Beat 任务单条 **3 秒**。
- **异常**：不裸 `except`；一律 `except Exception as e:` + `logger.exception(...)`。
- **不新增依赖**（`alibabacloud-oss-v2`、`websockets`、`requests` 都已在 requirements）。
- **不改数据库结构** —— D 批**没有迁移**（`status`/`owner` 等字段 C 批已立好）。
- 后端测试：`cd backend && D:/MyWork/Miniconda3/envs/py312/python.exe -m pytest web/tests/ -v`，基线 **274 passed, 3 deselected**。
- 前端测试：`cd frontend && npm run test:unit`，基线 **156 passed (19 files)**。

### 已核实的事实（动手前不用再查，全部有实测证据）

| 事实 | 证据 |
|---|---|
| OSS 凭据可用；桶 `gqyin-ai-friends`，region `cn-beijing`，endpoint `oss-cn-beijing.aliyuncs.com` | 只读探针 `list_objects_v2` → 200 |
| **桶 ACL 是 `public-read`** | `get_bucket_acl` → `public-read` |
| SDK：`PutObjectRequest(bucket, key, acl=...)` —— **第三个参数就是 `acl`** | `inspect.signature` |
| SDK：`Client.presign` / `put_object_acl` / `delete_object` 都存在 | `hasattr` 实测 |
| `query_voice` 可用且返回 `status`（线上那个音色实测为 `OK`） | 之前的只读探针 |
| `create_voice` 的报文字段 | 仓库既有原型 `voice/custom/create_voice.py` |
| Beat 调度形状 / Celery 任务注册写法 | `backend/settings.py:311`、`web/tasks/__init__.py` |

### ⚠️ Task 1 会在你的阿里云账号里做真实操作

Task 1 会**真的创建一个音色**（CosyVoice 创建免费）并**真的上传一个测试样本到 OSS**，验证结束后**两者都会删掉**。不这么做，spec 里"样本要求以实测为准（v3-flash 的档位未单独区分）"那条就永远只是个猜测，后面所有关于格式/时长/审核耗时的判断都没有依据。

---

### Task 0: 建分支并提交文档

**Files:**
- Modify: `docs/superpowers/specs/2026-09-13-voice-customization-design.md`（**已在工作区改好**：6 处 OSS 更正 + 你要求的"将来收紧桶"说明 + 风险 14 登记）
- Modify: `docs/superpowers/plans/2026-09-16-voice-customization-c.md`（1 处更正）
- Add: `docs/superpowers/plans/2026-09-17-voice-customization-d.md`（本文件）

- [ ] **Step 1**

```bash
git checkout -b feature/gqyin/voice-clone
```

- [ ] **Step 2**

```bash
git add docs/superpowers/specs/2026-09-13-voice-customization-design.md \
        docs/superpowers/plans/2026-09-16-voice-customization-c.md \
        docs/superpowers/plans/2026-09-17-voice-customization-d.md
git commit -m "docs(voice): OSS 实测更正 + D 批复刻接线实施计划"
```

---

### Task 1: 前置核实 —— 真实账号往返一次（**不落文件**）

这一步**不写进仓库**，用 `manage.py shell` 或本机 conda python 跑一次，把结论带回文档。

- [ ] **Step 1: 造一个测试样本**

用我们自己的 TTS 合成一段约 15 秒的 mp3（可控、不用你录、也不碰你桶里现有的文件）：

```python
# 在 backend 目录用 conda python 跑；synthesize_once 已在 web/utils/tts.py
import tempfile, os
from web.utils.tts import synthesize_once
text = ('你好呀，这是一段用来验证声音复刻接口的测试录音。'
        '我在这里连续说几句话，确保时长足够、吐字清晰、中间没有长时间停顿。'
        '如果你能听到这段声音，就说明合成链路是通的。')
audio = synthesize_once(text, 'longanyang')      # 复用内置音色，不需要账号额外配额
path = os.path.join(tempfile.gettempdir(), 'spike_sample.mp3')   # ⚠️ 别用 '/tmp'：Windows 上会落到 D:\tmp
open(path, 'wb').write(audio)
print('样本字节数:', len(audio), '->', path)
```

判定：字节数应在几十 KB 量级。**若不足 10 秒**（≈16KB/s × 10），把文案加长再合成一次。

- [ ] **Step 2: 上传到 OSS（对象级 private）并签名**

```python
import os, uuid, datetime
import alibabacloud_oss_v2 as oss
# 凭据从 backend/.env 读（键名 OSS_ACCESS_KEY_ID / SECRET / BUCKET / REGION / ENDPOINT）
cfg = oss.config.load_default()
cfg.credentials_provider = oss.credentials.StaticCredentialsProvider(
    access_key_id=..., access_key_secret=...)
cfg.region = ...; cfg.endpoint = ...
client = oss.Client(cfg)
key = f'spike/{uuid.uuid4().hex}.mp3'
with open(path, 'rb') as f:
    client.put_object(oss.PutObjectRequest(bucket=BUCKET, key=key, body=f, acl='private'))
# 验证对象级 ACL 真的生效（而不是继承了桶的 public-read）
info = client.get_object_acl(oss.GetObjectAclRequest(bucket=BUCKET, key=key))
print('对象 ACL =', info.acl)          # 期望 private
url = client.presign(oss.GetObjectRequest(bucket=BUCKET, key=key),
                     expires=datetime.timedelta(minutes=5)).url
print('签名 URL:', url[:120], '...')
```

- [ ] **Step 2b: 顺手验一件事 —— OSS 的错误码白名单凭什么是对的**

`oss.py` 的 `OSS_CONFIG_ERROR_CODES`（`InvalidAccessKeyId` / `SignatureDoesNotMatch` / `NoSuchBucket` / `AccessDenied` / `InvalidBucketName`）是**对着 OSS 文档写的知识**，离线验不出来：SDK 源码里除了 `NoSuchBucket`，另外四个字符串**一个都不出现**。所以"白名单与真实返回的 code 写法一致"只有真调一次才能证。用**故意写错的桶名**调一次，把真实形状打出来：

```python
try:
    client.get_bucket_acl(oss.GetBucketAclRequest(
        bucket='definitely-not-a-bucket-' + uuid.uuid4().hex[:6]))
except Exception as e:
    print('真实异常类型:', type(e).__name__)
    print('  code        =', getattr(e, 'code', None))
    print('  status_code =', getattr(e, 'status_code', None))
```

要确认三件事：① 类型确实是 `ServiceError`（而不是别的族）；② 属性名确实是 `.code`（源码里是 `self.code = kwargs.get("code", None)` ✓，但在真实实例上再确认一次）；③ **`code` 的写法与白名单字符串一致** —— 若不一致（大小写、后缀差异），把真实值回填进 `OSS_CONFIG_ERROR_CODES`，否则那条分支永远不命中、配置事故会悄悄退回 503（正是这几轮一直在收的那个洞）。

- [ ] **Step 3: 调 `create_voice`，然后按生产顺序立刻删样本、再轮询**

用 `.env` 里的 `VOICE_URL` + `API_KEY`（POST JSON，与原型 `voice/custom/create_voice.py` 同形）：

```python
import requests, json, re, time
payload = {'model': 'voice-enrollment', 'input': {
    'action': 'create_voice', 'target_model': 'cosyvoice-v3-flash',
    'prefix': 'spike' + uuid.uuid4().hex[:4],      # 字母数字、≤10 字符
    'url': url}}
r = requests.post(VOICE_URL, headers={'Authorization': f'Bearer {API_KEY}'}, json=payload, timeout=15)
print(r.status_code, json.dumps(r.json(), ensure_ascii=False)[:400])
new_voice_id = r.json().get('output', {}).get('voice_id')
```

⚠️ **紧接着就删掉 OSS 对象 —— 这一步的顺序是本 Task 的重点**：生产实现（Task 3）是「`create_voice` 返回后**立刻**删样本，然后再等审核」，所以只有**在这个顺序下**跑通，才能证明 spec §8 对用户的那句承诺（"复刻提交后立即删除"）真的成立：

```python
client.delete_object(oss.DeleteObjectRequest(bucket=BUCKET, key=key))
print('样本已删除，剩余 spike/ 对象:', client.list_objects_v2(
    oss.ListObjectsV2Request(bucket=BUCKET, prefix='spike/')).contents)
```

**判定**：删了样本之后仍然变成 `OK` → 说明阿里云在 `create_voice` 那一刻就把样本取走了，"立刻删"安全 ✓；若变成 `UNDEPLOYED` 或迟迟不动 → **说明它延迟拉取，生产实现必须改成"审核落地后再删"**，此时要停下来改 spec §6.2.6 与 §8 的措辞（改成长 TTL 或延迟删除）并报给用户，**不能带着这个假设继续**。

然后每 15 秒 `query_voice` 一次，记录 `status` 从什么变成什么、**花了多久**：

```python
for i in range(20):
    q = requests.post(VOICE_URL, headers={'Authorization': f'Bearer {API_KEY}'},
                      json={'model': 'voice-enrollment',
                            'input': {'action': 'query_voice', 'voice_id': new_voice_id}},
                      timeout=15).json()
    st = q.get('output', {}).get('status')
    print(f'第 {i} 次: status={st}')
    if st in ('OK', 'UNDEPLOYED'):
        break
    time.sleep(15)
```

- [ ] **Step 4: 把结论写进 spec**

在 spec §6.2 末尾（或风险 6 的位置）加一小节「实测结论（2026-09-17）」记录五件事：
① v3-flash **实际接受**的样本格式/时长/大小（以本次样本的实测值为准）；② 从提交到 `OK`（或 `UNDEPLOYED`）**实际耗时** —— 它决定 Beat 的 5 分钟节奏与 24 小时窗口是否够用；③ **样本在 `create_voice` 后立刻删除是否安全**（Step 3 那条判定）；④ 合成音样本**能不能**通过（若被拒，改用你桶里现成的 `hahaha.mp3` 重试一次并记录差异）；⑤ 对 `delete_voice` 传一个**不存在的** id 时的返回形状（Step 5 那步做的）—— 它决定 Task 5 怎么识别"阿里云侧已不存在 → 视为删除成功"。**若 `create_voice` 直接报错**（如 2038 无复刻权限），把错误码原文记下来并**停在这里报给用户**：那说明这条链路在当前账号状态下有阻塞。

- [ ] **Step 5: 清理（必做）**

```python
# 删掉刚建的音色
requests.post(VOICE_URL, headers={'Authorization': f'Bearer {API_KEY}'},
              json={'model': 'voice-enrollment',
                    'input': {'action': 'delete_voice', 'voice_id': new_voice_id}}, timeout=15)
# 再删一次同一个 id —— 只为看"不存在"时的返回形状（Task 5 要靠它识别）
r2 = requests.post(VOICE_URL, headers={'Authorization': f'Bearer {API_KEY}'},
                   json={'model': 'voice-enrollment',
                         'input': {'action': 'delete_voice', 'voice_id': new_voice_id}}, timeout=15)
print('重复删除的返回:', r2.status_code, r2.text[:300])
```

验证：`list_objects_v2` 里不再有 `spike/` 前缀的对象；`query_voice` 对 `new_voice_id` 返回不存在。

- [ ] **Step 6: 提交文档更新**

```bash
git add docs/superpowers/specs/2026-09-13-voice-customization-design.md
git commit -m "docs(voice): D 批样本格式与审核耗时的实测结论"
```

---

### Task 2: OSS 工具 —— 上传（对象级 private）/ 签名 / 删除

**Files:**
- Create: `backend/web/utils/oss.py`
- Test: `backend/web/tests/test_voice_clone.py`（新建）

**Interfaces:**
- Produces: `upload_private(local_bytes, suffix) -> str`（返回对象 key）、`presign_get(key, minutes=5) -> str`、`delete_object_quietly(key) -> None`
- Produces: `OssConfigError`（配置/凭据/权限/命名类错 → 调用方转 **500**）、`OssUnavailableError`（其余 → **503**）
- 全部 **5 秒超时**；凭据与桶名从环境变量读，缺任何一个都抛 **`OssConfigError`**（让调用方转 500 并指出缺哪个变量）；其它 OSS 异常一律归一成 `OssUnavailableError`

- [ ] **Step 1: 写失败测试**

```python
class TestOssUtil:
    def test_missing_env_raises_config_error(self, monkeypatch):
        from web.utils import oss as oss_util
        monkeypatch.delenv('OSS_BUCKET', raising=False)
        with pytest.raises(oss_util.OssConfigError) as e:
            oss_util._client()
        assert 'OSS_BUCKET' in str(e.value)

    def test_classifies_config_vs_unavailable(self):
        """把 SDK 的异常体系归一成两类（实测：SDK 的 24 个异常类没有一个继承 RuntimeError）"""
        import alibabacloud_oss_v2.exceptions as ex
        from web.utils.oss import OssConfigError, OssUnavailableError, _wrap

        def _raise(e):
            return lambda: (_ for _ in ()).throw(e)

        # 凭据错 → 配置错（500），不能当成"上游抖动"
        with pytest.raises(OssConfigError):
            _wrap(_raise(ex.CredentialsEmptyError()))
        # 客户端参数/命名校验族 → 同样是我们写错了 → 500
        # ⚠️ 这族必须带**关键字**参数构造（实测 1.2.5）：`ParamRequiredError()` 抛
        #    KeyError('field')、`BucketNameInvalidError()` 抛 KeyError('name')
        with pytest.raises(OssConfigError):
            _wrap(_raise(ex.ParamRequiredError(field='x')))
        with pytest.raises(OssConfigError):
            _wrap(_raise(ex.BucketNameInvalidError(name='bad')))
        # bucket 不存在这种带 code 的服务端错 → 也是配置错
        # ⚠️ `ServiceError` 的构造要求一串必填字段（实测依次要 status_code / code /
        #    request_id / ec …），去凑它的构造签名只会把用例写脆 ——
        #    改用 `__new__` 绕过构造再赋 code（实测可行，且 isinstance 依然成立）
        svc = ex.ServiceError.__new__(ex.ServiceError)
        svc.code = 'NoSuchBucket'
        with pytest.raises(OssConfigError):
            _wrap(_raise(svc))
        # 其它（超时/网络）→ 上游不可用（503）
        with pytest.raises(OssUnavailableError):
            _wrap(_raise(TimeoutError('slow')))
        # ⚠️ 自家异常必须原样放行：若被重新包成另一类，上面两条会有一半失效
        with pytest.raises(OssConfigError):
            _wrap(_raise(OssConfigError('x')))
        with pytest.raises(OssUnavailableError):
            _wrap(_raise(OssUnavailableError('x')))

    def test_config_error_type_names_still_exist(self):
        """软取的代价要配守卫：某个名字将来被改名/删除时，这一族会**静默**退回 503"""
        import alibabacloud_oss_v2.exceptions as ex
        from web.utils.oss import _CONFIG_ERROR_TYPE_NAMES

        for n in _CONFIG_ERROR_TYPE_NAMES:
            assert hasattr(ex, n), f'SDK 里已没有 {n}，软取的分类会静默失效'

    def test_missing_env_surfaces_as_config_error_through_upload(self, monkeypatch):
        """走**完整路径**（经 `_wrap`）而不是直接调 `_client()`

        守卫的由来：`_client()` 在 `_wrap` 的 lambda *内部*，若 `_wrap` 不放行自家异常，
        缺环境变量会被重包成 `OssUnavailableError` → 视图返 503，而 spec §7 要的是 500。
        """
        from web.utils.oss import OssConfigError, upload_private

        monkeypatch.delenv('OSS_BUCKET', raising=False)
        with pytest.raises(OssConfigError):
            upload_private(b'ID3x')

    def test_upload_sets_object_private_and_returns_key(self, monkeypatch):
        """对象级 ACL 必须是 private —— 桶是 public-read，不能依赖桶设置"""
        from web.utils import oss as oss_util
        calls = {}

        class _FakeClient:
            def put_object(self, req):
                calls['put'] = req
            def presign(self, req, expires=None):
                calls['presign'] = req
                return type('R', (), {'url': 'https://signed.example/x'})()
            def delete_object(self, req):
                calls['del'] = req

        monkeypatch.setattr(oss_util, '_client', lambda: _FakeClient())
        key = oss_util.upload_private(b'ID3bytes', 'mp3')
        assert calls['put'].acl == 'private'          # 关键断言
        assert calls['put'].key == key
        assert oss_util.presign_get(key) == 'https://signed.example/x'

    def test_delete_is_quiet_when_upstream_fails(self, monkeypatch, caplog):
        """删除失败不能抛 —— 它在 finally 里，抛出去会盖掉真正的错误"""
        from web.utils import oss as oss_util

        class _Boom:
            def delete_object(self, req):
                raise RuntimeError('boom')

        monkeypatch.setattr(oss_util, '_client', lambda: _Boom())
        oss_util.delete_object_quietly('spike/x.mp3')   # 不抛
```

- [ ] **Step 2: 跑测试确认失败**

Run: `... -m pytest web/tests/test_voice_clone.py -v -k TestOssUtil`
Expected: 全 FAIL（模块不存在）。

- [ ] **Step 3: 实现**

`backend/web/utils/oss.py`：

```python
"""OSS 上传/签名/删除 —— 样本是用户语音，必须对象级私有 + 短期签名。

桶（OSS_BUCKET）实测是 public-read，所以**不能**依赖桶级设置：每个对象上传时显式 acl='private'。
"""
import datetime
import logging
import os
import uuid

import alibabacloud_oss_v2 as oss

logger = logging.getLogger(__name__)

OSS_TIMEOUT_SECONDS = 5
SAMPLE_PREFIX = 'samples/'

# "配置/凭据/权限"类服务端错误码 —— 归 500（给运维看），其余归 503（上游抖动）
OSS_CONFIG_ERROR_CODES = {
    'InvalidAccessKeyId', 'SignatureDoesNotMatch', 'NoSuchBucket',
    'AccessDenied', 'InvalidBucketName',
}

# SDK 侧"参数/命名"类异常 —— 同样是我们这边配置或代码写错了（如 OSS_BUCKET 写成非法桶名），
# 按 spec §7 归 500。用名字软取、不硬写类引用：某个名字在别的 SDK 版本里不存在时不会让 import 崩。
_CONFIG_ERROR_TYPE_NAMES = (
    'CredentialsBaseError', 'ParamInvalidError', 'ParamRequiredError',
    'ParamNullOrEmptyError', 'ParamNullError',
    'BucketNameInvalidError', 'ObjectNameInvalidError',
)
OSS_CONFIG_ERROR_TYPES = tuple(
    t for t in (getattr(oss.exceptions, n, None) for n in _CONFIG_ERROR_TYPE_NAMES)
    if isinstance(t, type))


class OssConfigError(Exception):
    """OSS 配置/凭据/权限错 —— 调用方应转 **500** 并打 ERROR 日志（spec §7）。"""


class OssUnavailableError(Exception):
    """OSS 上游不可用/超时 —— 调用方应转 **503**。"""


def _is_config_error(e: Exception) -> bool:
    """把 SDK 的异常体系收敛成"配置错 / 上游错"两类。

    ⚠️ 不能只判 `RuntimeError`：实测 SDK 的 **24 个异常类没有一个继承 `RuntimeError`**
    （`BaseError` / `ServiceError` / `CredentialsEmptyError` 都直接继承 `Exception`），
    所以"凭据错、bucket 不存在"这类**配置事故**会漏进兜底、被当成"上游抖动"返 503。

    ⚠️ 已知边界（Task 1 实测）：**桶名写错/桶不存在**时 SDK 抛的是 `OperationError`（`code=None`），
    与"网络不可达"**同一个异常类型、无法区分** → 这类会落到 503（可重试）而不是 500。
    白名单对"服务端带 code 的鉴权错"（如 `InvalidAccessKeyId`）仍然有效。
    不为了对齐文档去硬拆一个拆不开的东西 —— 用"打全量 ERROR 日志给运维"补足即可。
    """
    if isinstance(e, (RuntimeError, *OSS_CONFIG_ERROR_TYPES)):
        return True
    if isinstance(e, oss.exceptions.ServiceError):
        return (getattr(e, 'code', '') or '') in OSS_CONFIG_ERROR_CODES
    return False


def _wrap(fn):
    """跑一次 OSS 调用，把 SDK 异常归一成上面两个自有异常（SDK 分类知识只留在本模块）。

    ⚠️ **自家异常必须原样放行**：`_client()` 是在本函数的 lambda *内部* 调用的，而它自己也抛
    `OssConfigError` —— 不先放行就会被下面的兜底重新包成 `OssUnavailableError`，
    于是"缺环境变量"从 500 退化成 503（这条路径在收敛之前反而是对的，别把它改回去）。
    """
    try:
        return fn()
    except (OssConfigError, OssUnavailableError):
        raise
    except Exception as e:
        if _is_config_error(e):
            raise OssConfigError(str(e)) from e
        raise OssUnavailableError(str(e)) from e


def _client():
    missing = [k for k in ('OSS_ACCESS_KEY_ID', 'OSS_ACCESS_KEY_SECRET',
                           'OSS_BUCKET', 'OSS_REGION', 'OSS_ENDPOINT')
               if not os.getenv(k)]
    if missing:
        raise OssConfigError(f'OSS 配置缺失: {", ".join(missing)}')
    cfg = oss.config.load_default()
    cfg.credentials_provider = oss.credentials.StaticCredentialsProvider(
        access_key_id=os.environ['OSS_ACCESS_KEY_ID'],
        access_key_secret=os.environ['OSS_ACCESS_KEY_SECRET'])
    cfg.region = os.environ['OSS_REGION']
    cfg.endpoint = os.environ['OSS_ENDPOINT']
    cfg.connect_timeout = OSS_TIMEOUT_SECONDS
    cfg.readwrite_timeout = OSS_TIMEOUT_SECONDS
    return oss.Client(cfg)


def upload_private(data: bytes, suffix: str = 'mp3') -> str:
    """上传为**对象级 private**，返回对象 key。调用方负责用 presign_get 换签名 URL。"""
    key = f'{SAMPLE_PREFIX}{uuid.uuid4().hex}.{suffix}'
    _wrap(lambda: _client().put_object(oss.PutObjectRequest(
        bucket=os.environ['OSS_BUCKET'], key=key, body=data, acl='private')))
    return key


def presign_get(key: str, minutes: int = 5) -> str:
    req = oss.GetObjectRequest(bucket=os.environ['OSS_BUCKET'], key=key)
    return _wrap(lambda: _client().presign(
        req, expires=datetime.timedelta(minutes=minutes)).url)


def delete_object_quietly(key: str) -> None:
    """best-effort 删除：在 finally 里调用，绝不能把真正的错误盖掉。"""
    try:
        _client().delete_object(
            oss.DeleteObjectRequest(bucket=os.environ['OSS_BUCKET'], key=key))
    except Exception:
        logger.exception('OSS 对象删除失败（需人工清理）: key=%s', key)
```

（`connect_timeout` / `readwrite_timeout` 已核实是 `alibabacloud-oss-v2` `Config` 的真实字段名；`GetObjectRequest` / `GetObjectAclRequest` / `get_object_acl` 也都实测存在。）

- [ ] **Step 4: 跑测试确认通过**

Run: `... -m pytest web/tests/test_voice_clone.py -q` → 全绿。

- [ ] **Step 5: 提交**

```bash
git add backend/web/utils/oss.py backend/web/tests/test_voice_clone.py
git commit -m "feat(voice): OSS 工具 —— 对象级私有上传 + 短期签名 + 静默删除"
```

---

### Task 3: `clone` 端点

**Files:**
- Create: `backend/web/views/create/character/voice/clone.py`
- Modify: `backend/web/urls.py`
- Modify: `backend/web/views/create/character/voice/visibility.py`（加配额常量与计数函数）
- Test: `backend/web/tests/test_voice_clone.py`（追加）

**Interfaces:**
- Produces: `VOICE_QUOTA_PER_USER = 5`、`USER_VOICE_COUNT_WARN = 800`（全平台水位告警阈值）
- Produces: `POST /api/create/character/voice/clone/`，multipart：`file` / `name` / `profile`

- [ ] **Step 1: 写失败测试**（全部 mock 掉 OSS 与阿里云，测试不碰网络）

```python
CLONE = 'web.views.create.character.voice.clone'


def _mp3(name='s.mp3', data=b'ID3fakeaudio'):
    """带 ID3 头的假 mp3 —— 能过 magic byte 校验（后缀对了但内容不是音频的用例另写）"""
    return SimpleUploadedFile(name, data, content_type='audio/mpeg')


class TestCloneGuards:
    """参数/授权/配额的闸门 —— 这些必须在碰 OSS 之前挡住"""

    def test_missing_name_returns_400(self, auth_client):
        resp = auth_client.post('/api/create/character/voice/clone/',
                                {'file': _mp3(), 'consent': 'true'})
        assert resp.status_code == 400

    def test_missing_consent_returns_400(self, auth_client):
        """spec §6.2.1 / §8：授权声明必须勾选，后端也要挡住（不能只靠前端）"""
        with patch(f'{CLONE}.upload_private') as up:
            resp = auth_client.post('/api/create/character/voice/clone/',
                                    {'file': _mp3(), 'name': 'n'})
        assert resp.status_code == 400
        assert '授权' in resp.json()['message']
        assert up.call_count == 0

    def test_oversize_returns_400(self, auth_client):
        big = SimpleUploadedFile('s.mp3', b'ID3' + b'x' * (8 * 1024 * 1024), content_type='audio/mpeg')
        resp = auth_client.post('/api/create/character/voice/clone/',
                                {'file': big, 'name': 'n', 'consent': 'true'})
        assert resp.status_code == 400
        assert '8' in resp.json()['message']          # 提示里要有上限

    def test_bad_extension_returns_400(self, auth_client):
        resp = auth_client.post('/api/create/character/voice/clone/',
                                {'file': SimpleUploadedFile('s.txt', b'x'),
                                 'name': 'n', 'consent': 'true'})
        assert resp.status_code == 400

    def test_fake_extension_rejected_by_magic_bytes(self, auth_client):
        """后缀是 mp3、内容不是音频 → 400，且不碰 OSS（spec §6.2.3 要求 magic byte）"""
        fake = SimpleUploadedFile('fake.mp3', b'this is not audio', content_type='audio/mpeg')
        with patch(f'{CLONE}.upload_private') as up:
            resp = auth_client.post('/api/create/character/voice/clone/',
                                    {'file': fake, 'name': 'n', 'consent': 'true'})
        assert resp.status_code == 400
        assert up.call_count == 0

    def test_quota_exceeded_returns_400(self, auth_client, user_profile):
        for i in range(5):
            Voice.objects.create(name=f'v{i}', voice_id=f'q_{i}',
                                 owner=user_profile, visibility='private')
        with patch(f'{CLONE}.upload_private') as up:
            resp = auth_client.post('/api/create/character/voice/clone/',
                                    {'file': _mp3(), 'name': 'n', 'consent': 'true'})
        assert resp.status_code == 400
        assert up.call_count == 0                     # 配额不过就不该碰 OSS


class TestCloneFlow:
    def test_success_creates_deploying_row_and_deletes_sample(self, auth_client,
                                                             user_profile, caplog):
        with patch(f'{CLONE}.upload_private', return_value='samples/x.mp3'), \
             patch(f'{CLONE}.presign_get', return_value='https://signed/x'), \
             patch(f'{CLONE}.create_voice', return_value='cosyvoice-v3-flash-new-abc') as cv, \
             patch(f'{CLONE}.delete_object_quietly') as rm:
            resp = auth_client.post('/api/create/character/voice/clone/',
                                    {'file': _mp3(), 'name': '我的音色', 'profile': '温柔',
                                     'consent': 'true'})
        assert resp.status_code == 200
        v = Voice.objects.get(owner=user_profile)
        assert v.status == 'deploying' and v.visibility == 'private'
        assert v.voice_id == 'cosyvoice-v3-flash-new-abc'
        assert cv.call_count == 1
        assert rm.call_count == 1                     # 提交后立即删样本
        assert 'consent=true' in caplog.text          # 声明落日志（spec §8，一期不落库）

    def test_aliyun_rejection_returns_400_and_creates_no_row(self, auth_client, user_profile):
        with patch(f'{CLONE}.upload_private', return_value='samples/x.mp3'), \
             patch(f'{CLONE}.presign_get', return_value='https://signed/x'), \
             patch(f'{CLONE}.create_voice', side_effect=AliyunRejected('400 InvalidParameter')), \
             patch(f'{CLONE}.delete_object_quietly') as rm:
            resp = auth_client.post('/api/create/character/voice/clone/',
                                    {'file': _mp3(), 'name': 'n', 'consent': 'true'})
        assert resp.status_code == 400
        assert not Voice.objects.filter(owner=user_profile).exists()
        assert rm.call_count == 1                     # 失败路径也要删样本
        # 措辞不能断言"样本有问题"：账号配额耗尽等也会走到这里
        assert '未通过审核' not in resp.json()['message']

    def test_upstream_unavailable_returns_503(self, auth_client, user_profile):
        with patch(f'{CLONE}.upload_private', return_value='samples/x.mp3'), \
             patch(f'{CLONE}.presign_get', return_value='https://signed/x'), \
             patch(f'{CLONE}.create_voice', side_effect=TimeoutError()):
            resp = auth_client.post('/api/create/character/voice/clone/',
                                    {'file': _mp3(), 'name': 'n', 'consent': 'true'})
        assert resp.status_code == 503
        assert not Voice.objects.filter(owner=user_profile).exists()

    def test_oss_config_error_returns_500_not_503(self, auth_client, user_profile):
        """OSS 配置/凭据错 → 500（给运维），与"上游不可用 → 503"分成两档（spec §7）

        实测 SDK 的 24 个异常类**都不继承 RuntimeError**，所以这条走的是 `oss.py` 归一出来的
        `OssConfigError` —— 只 catch `RuntimeError` 会把"凭据错/bucket 不存在"误判成 503。
        """
        from web.utils.oss import OssConfigError

        with patch(f'{CLONE}.upload_private',
                   side_effect=OssConfigError('OSS 配置缺失: OSS_BUCKET')):
            resp = auth_client.post('/api/create/character/voice/clone/',
                                    {'file': _mp3(), 'name': 'n', 'consent': 'true'})
        assert resp.status_code == 500
        assert not Voice.objects.filter(owner=user_profile).exists()

    def test_accepts_common_mp3_frame_syncs(self):
        """帧同步用**位掩码**判定而不是枚举字节对：\\xff\\xfa（带 CRC）等也要收 —— 误拒合法文件
        比误收更糟（误收最多被阿里云拒一次）"""
        from web.views.create.character.voice.clone import looks_like_audio

        for head in (b'ID3', b'\xff\xfb', b'\xff\xfa', b'\xff\xf3', b'\xff\xf2',
                     b'\xff\xe3', b'\xff\xe2'):
            assert looks_like_audio(head + b'\x00' * 16, 'mp3') is True
        assert looks_like_audio(b'this is not audio', 'mp3') is False
        assert looks_like_audio(b'RIFF' + b'\x00' * 8, 'wav') is True
        assert looks_like_audio(b'\x00\x00\x00\x20ftypM4A ', 'm4a') is True
```

（异常与导入说明：`AliyunRejected` = 阿里云**明确拒绝** → 400；`AliyunUnavailable` 或任意其它异常 → 503；**OSS 配置类错误用 `RuntimeError` 识别 → 500**（spec §7 把"配置错"与"上游抖动"分成两档）；`AliyunNotFound` 在 Task 5 的删除路径里用（= 阿里云侧已不存在 → 视为删除成功）。顶部需要 `from unittest.mock import patch`、`from django.core.files.uploadedfile import SimpleUploadedFile`、`from django.db.models import RestrictedError`、`from rest_framework import status`。）

- [ ] **Step 2: 跑测试确认失败**

Run: `... -m pytest web/tests/test_voice_clone.py -v -k TestClone` → 全 FAIL（URL 未注册；注意本项目 SPA catch-all 会让未注册路径返回 **200** 而不是 404，所以断言 `status_code == 400` 会以"200 != 400"的形式失败，这是对的）。

- [ ] **Step 3: 实现**

`visibility.py` 追加：

```python
VOICE_QUOTA_PER_USER = 5
USER_VOICE_COUNT_WARN = 800       # 全平台水位告警（1000 是账号级上限）


def user_voice_count(profile):
    return Voice.objects.filter(owner=profile).count()
```

`clone.py`：

```python
"""音色复刻：上传样本 → OSS(对象级 private) → 签名 URL → 阿里云 create_voice。

铁律：样本**无论成败都立即删除**；同步失败**不建行**（拿不到阿里云 id 时硬塞一行等于让字段说谎）。
"""
import logging
import os

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.character import Voice
from web.utils.oss import (OssConfigError, delete_object_quietly, presign_get,
                           upload_private)
from web.views.create.character.voice.visibility import (VOICE_QUOTA_PER_USER,
                                                         user_voice_count)

logger = logging.getLogger(__name__)

MAX_SAMPLE_BYTES = 8 * 1024 * 1024          # nginx client_max_body_size 是 10m，留出 multipart 余量
ALLOWED_SUFFIXES = {'mp3', 'wav', 'm4a'}
NAME_MAX_LEN = 100                          # 与 Voice.name 的 max_length 对齐
PROFILE_MAX_LEN = 500
REQUEST_TIMEOUT = 5
CONSENT_TRUE = {'true', '1', 'on', 'yes'}


def looks_like_audio(data: bytes, suffix: str) -> bool:
    """magic byte 校验（spec §6.2.3）。

    ⚠️ 不能照搬 `views/document/upload.py:21` 那张 MAGIC_BYTES 表：它里面**没有音频项**，
    而且 m4a 的 `ftyp` 在**第 4 字节**而不是开头 —— 所以这里单独写一个。
    """
    if suffix == 'mp3':
        # 有 ID3 头就收；否则看**帧同步**：0xFF 后高 3 位全 1 —— 位掩码一次覆盖
        # \xff\xfb / \xff\xfa / \xff\xf3 / \xff\xf2 / \xff\xe3 / \xff\xe2，
        # 而枚举字节对会漏（\xff\xfa 是带 CRC 的 MPEG-1 Layer III，实际文件里常见）。
        # 方向也重要：误拒合法文件比误收更糟（误收最多被阿里云拒一次）。
        return data[:3] == b'ID3' or (len(data) > 1 and data[0] == 0xFF
                                      and (data[1] & 0xE0) == 0xE0)
    if suffix == 'wav':
        return data[:4] == b'RIFF'
    if suffix == 'm4a':
        return data[4:8] == b'ftyp'
    return False


class AliyunRejected(Exception):
    """阿里云**明确拒绝**（样本不合格 / 敏感内容 / 2038 无复刻权限）→ 400。"""


class AliyunUnavailable(Exception):
    """上游不可用或超时 → 503。"""


def create_voice(url, prefix):
    """调 voice-enrollment 的 create_voice。5 秒超时。"""
    import requests
    payload = {'model': 'voice-enrollment', 'input': {
        'action': 'create_voice', 'target_model': 'cosyvoice-v3-flash',
        'prefix': prefix, 'url': url}}
    try:
        resp = requests.post(os.getenv('VOICE_URL'),
                             headers={'Authorization': f'Bearer {os.getenv("API_KEY")}'},
                             json=payload, timeout=REQUEST_TIMEOUT)
    except Exception as e:
        raise AliyunUnavailable(str(e)) from e
    data = resp.json() if resp.content else {}
    out = data.get('output') or {}
    if resp.status_code != 200 or not out.get('voice_id'):
        # 2038=无复刻权限、样本不合格、敏感内容 —— 都归"明确拒绝"
        raise AliyunRejected(f'{resp.status_code} {data.get("code", "")} {data.get("message", "")}'[:300])
    return out['voice_id']


class CloneVoiceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sample = request.FILES.get('file')
        name = (request.data.get('name') or '').strip()
        profile = (request.data.get('profile') or '').strip()
        consent = str(request.data.get('consent', '')).lower()

        if not name or len(name) > NAME_MAX_LEN:
            return Response({'message': f'音色名称必填且不超过 {NAME_MAX_LEN} 字'}, status=400)
        if len(profile) > PROFILE_MAX_LEN:
            return Response({'message': f'音色描述不超过 {PROFILE_MAX_LEN} 字'}, status=400)
        if consent not in CONSENT_TRUE:
            # spec §6.2.1 / §8：样本是用户的声音，必须先拿到授权声明（后端也要挡，不只靠前端）
            return Response({'message': '请先确认授权声明：这是本人声音，或已获得声音权利人授权'},
                            status=400)
        if not sample:
            return Response({'message': '请上传声音样本'}, status=400)
        if sample.size > MAX_SAMPLE_BYTES:
            return Response({'message': f'样本不得超过 {MAX_SAMPLE_BYTES // 1024 // 1024}MB'}, status=400)
        suffix = (sample.name.rsplit('.', 1)[-1] if '.' in sample.name else '').lower()
        if suffix not in ALLOWED_SUFFIXES:
            return Response({'message': '样本格式只支持 mp3 / wav / m4a'}, status=400)
        data = sample.read()
        if not looks_like_audio(data, suffix):
            return Response({'message': '样本内容不是有效的音频文件'}, status=400)

        profile_obj = request.user.userprofile
        if user_voice_count(profile_obj) >= VOICE_QUOTA_PER_USER:
            return Response({'message': f'最多只能创建 {VOICE_QUOTA_PER_USER} 个音色'}, status=400)

        key = None
        try:
            key = upload_private(data, suffix)
            url = presign_get(key)                       # 5 分钟有效
            prefix = f'vf{profile_obj.id}{uuid.uuid4().hex[:4]}'   # 字母数字、≤10
            logger.info('复刻请求: consent=true user=%s name=%s prefix=%s',
                        profile_obj.id, name, prefix)
            voice_id = create_voice(url, prefix)
        except OssConfigError as e:
            # OSS 配置/凭据/权限错 —— 不是用户的错，也不是上游抖动，归 500 给运维（spec §7 两档分开）
            logger.error('OSS 配置错误，复刻不可用: %s', e)
            return Response({'message': '复刻服务未正确配置，请联系管理员'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except AliyunRejected as e:
            # 措辞刻意**不断言"样本有问题"**：账号配额耗尽、上游策略变化等也会走到这里，
            # 把上游原文带上（含 code），日志里留全量
            logger.warning('复刻被阿里云拒绝: %s', e)
            return Response({'message': f'复刻未成功（上游拒绝：{e}）'}, status=400)
        except Exception as e:
            logger.exception('复刻失败（上游不可用）: %s', e)
            return Response({'message': '复刻服务暂时不可用，请稍后再试'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        finally:
            if key:
                delete_object_quietly(key)               # 无论成败都删样本

        voice = Voice.objects.create(name=name, voice_id=voice_id, profile=profile,
                                     owner=profile_obj, visibility='private',
                                     status='deploying')
        return Response({'message': 'success',
                         'voice': {'id': voice.id, 'status': voice.status}})
```

（`uuid` 需 import；`prefix` 用 `vf` + profile id + 4 位随机 —— 字母数字、长度 ≤10。配额与水位告警的判定放这里，全平台水位那条在 Task 4 的 Beat 任务里记 warning。）

`urls.py` 加：

```python
from web.views.create.character.voice.clone import CloneVoiceView
    path('api/create/character/voice/clone/', CloneVoiceView.as_view()),
```

- [ ] **Step 4: 跑测试确认通过**

Run: `... -m pytest web/tests/ -q` → 全绿。

- [ ] **Step 5: 提交**

```bash
git add backend/web/views/create/character/voice/ backend/web/urls.py backend/web/tests/test_voice_clone.py
git commit -m "feat(voice): 复刻端点 —— 样本即传即删，失败不建行"
```

---

### Task 4: Beat 状态刷新任务

**Files:**
- Create: `backend/web/tasks/voice_status.py`
- Modify: `backend/web/tasks/__init__.py`（注册）
- Modify: `backend/backend/settings.py`（`CELERY_BEAT_SCHEDULE` 加一条）
- Test: `backend/web/tests/test_voice_clone.py`（追加）

**Interfaces:**
- Produces: `refresh_deploying_voices()`（Beat 每 5 分钟调一次）

- [ ] **Step 1: 写失败测试**

```python
class TestStatusRefresh:
    def test_ok_becomes_ready(self, db):
        from web.tasks.voice_status import refresh_deploying_voices
        v = Voice.objects.create(name='v', voice_id='ok_1', status='deploying')
        with patch('web.tasks.voice_status.query_status', return_value='OK'):
            refresh_deploying_voices()
        v.refresh_from_db(); assert v.status == 'ready'

    def test_undeployed_becomes_rejected(self, db):
        ...  # 同上，返回 'UNDEPLOYED' → 'rejected'

    def test_skips_rows_older_than_24h(self, db):
        """24 小时窗口之外的不再查询（避免长期 deploying 的行被无限重试）"""
        v = Voice.objects.create(name='v', voice_id='old_1', status='deploying')
        Voice.objects.filter(pk=v.pk).update(created_at=timezone.now() - timedelta(hours=25))
        with patch('web.tasks.voice_status.query_status') as q:
            refresh_deploying_voices()
        assert q.call_count == 0

    def test_one_failure_does_not_block_others(self, db):
        """单条抛异常不能影响其余行"""
        a = Voice.objects.create(name='a', voice_id='f_1', status='deploying')
        b = Voice.objects.create(name='b', voice_id='f_2', status='deploying')
        with patch('web.tasks.voice_status.query_status',
                   side_effect=[RuntimeError('boom'), 'OK']):
            refresh_deploying_voices()
        b.refresh_from_db(); assert b.status == 'ready'

    def test_batch_limit(self, db):
        """单轮上限 20 条，避免占满单并发 worker"""
        for i in range(25):
            Voice.objects.create(name=f'v{i}', voice_id=f'b_{i}', status='deploying')
        with patch('web.tasks.voice_status.query_status', return_value='OK') as q:
            refresh_deploying_voices()
        assert q.call_count == 20
```

- [ ] **Step 2: 跑测试确认失败** → 模块不存在。

- [ ] **Step 3: 实现**

`backend/web/tasks/voice_status.py`：

```python
"""复刻音色的状态刷新 —— 用 Beat 周期任务，不用长轮询。

为什么不用"提交后起一个 Celery 任务轮询到出结果"：`CELERY_TASK_SOFT_TIME_LIMIT=120` /
`TIME_LIMIT=180`、worker 是 `-c 1`，长轮询会被硬超时杀掉并堵住文档处理与记忆总结。
"""
import logging
import os

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

BATCH_LIMIT = 20                  # 单轮上限
FRESH_HOURS = 24                  # 只处理 24 小时内创建的行
QUERY_TIMEOUT = 3                 # 单条查询超时
WATERMARK = 800                   # 全平台音色数告警水位（1000 是账号级上限）


def query_status(voice_id):
    """返回阿里云侧的 status（'OK' / 'DEPLOYING' / 'UNDEPLOYED'）。"""
    import requests
    resp = requests.post(os.getenv('VOICE_URL'),
                         headers={'Authorization': f'Bearer {os.getenv("API_KEY")}'},
                         json={'model': 'voice-enrollment',
                               'input': {'action': 'query_voice', 'voice_id': voice_id}},
                         timeout=QUERY_TIMEOUT)
    return ((resp.json().get('output') or {}).get('status') or '').upper()


@shared_task
def refresh_deploying_voices():
    from web.models.character import Voice

    cutoff = timezone.now() - timezone.timedelta(hours=FRESH_HOURS)
    rows = list(Voice.objects.filter(status='deploying', created_at__gte=cutoff)
                .order_by('created_at')[:BATCH_LIMIT])
    if not rows:
        return {'checked': 0}

    total = Voice.objects.count()
    if total >= WATERMARK:
        logger.warning('音色总数已达水位: %d（账号上限 1000，请清理）', total)

    checked = changed = 0
    for v in rows:
        checked += 1
        try:
            st = query_status(v.voice_id)
        except Exception:
            logger.exception('查询音色状态失败，保持原状态: voice=%s', v.id)
            continue                          # fail-open：单条失败不影响其余
        if st == 'OK' and v.status != 'ready':
            v.status = 'ready'; v.save(update_fields=['status']); changed += 1
        elif st == 'UNDEPLOYED' and v.status != 'rejected':
            v.status = 'rejected'; v.save(update_fields=['status']); changed += 1
    return {'checked': checked, 'changed': changed}
```

`web/tasks/__init__.py` 加一行（与既有三条同形）：

```python
from web.tasks.voice_status import refresh_deploying_voices  # noqa: F401
```

`settings.py` 的 `CELERY_BEAT_SCHEDULE` 加：

```python
    'voice-status-sweep': {
        'task': 'web.tasks.voice_status.refresh_deploying_voices',
        'schedule': crontab(minute='*/5'),
    },
```

- [ ] **Step 4: 跑测试确认通过** → 全绿。

- [ ] **Step 5: 提交**

```bash
git add backend/web/tasks/ backend/backend/settings.py backend/web/tests/test_voice_clone.py
git commit -m "feat(voice): Beat 任务每 5 分钟刷新复刻音色状态"
```

---

### Task 5: `remove` 端点 —— 同步删阿里云侧

**Files:**
- Create: `backend/web/views/create/character/voice/remove.py`
- Modify: `backend/web/urls.py`
- Test: `backend/web/tests/test_voice_clone.py`（追加）

**Interfaces:**
- Produces: `POST /api/create/character/voice/remove/`，表单字段 `voice`

- [ ] **Step 1: 写失败测试**

```python
class TestRemoveVoice:
    def test_removes_own_unused_voice_and_calls_aliyun(self, auth_client, user_profile):
        v = Voice.objects.create(name='m', voice_id='rm_1', owner=user_profile,
                                 visibility='private')
        with patch(REMOVE + '.delete_voice') as dv:
            resp = auth_client.post('/api/create/character/voice/remove/', {'voice': v.id})
        assert resp.status_code == 200
        assert not Voice.objects.filter(id=v.id).exists()
        assert dv.call_count == 1

    def test_voice_in_use_returns_400_without_calling_aliyun(self, auth_client, character):
        with patch(REMOVE + '.delete_voice') as dv:
            resp = auth_client.post('/api/create/character/voice/remove/',
                                    {'voice': character.voice_id})
        assert resp.status_code == 400
        assert '角色' in resp.json()['message']
        assert dv.call_count == 0            # 本地就能判定，不该白跑一趟上游

    def test_others_voice_returns_404_same_message(self, auth_client, user_profile):
        other = UserProfile.objects.create(user=User.objects.create_user('rm_other'))
        v = Voice.objects.create(name='o', voice_id='rm_2', owner=other, visibility='private')
        r1 = auth_client.post('/api/create/character/voice/remove/', {'voice': v.id})
        r2 = auth_client.post('/api/create/character/voice/remove/', {'voice': 999999})
        assert r1.status_code == r2.status_code == 404
        assert r1.json()['message'] == r2.json()['message']

    def test_aliyun_failure_keeps_row(self, auth_client, user_profile):
        v = Voice.objects.create(name='m', voice_id='rm_3', owner=user_profile,
                                 visibility='private')
        with patch(REMOVE + '.delete_voice', side_effect=RuntimeError('boom')):
            resp = auth_client.post('/api/create/character/voice/remove/', {'voice': v.id})
        assert resp.status_code == 503
        assert Voice.objects.filter(id=v.id).exists()      # 保住 id 以便重试

    def test_aliyun_not_found_still_deletes_local_row(self, auth_client, user_profile):
        """阿里云侧已被 1 年规则清理掉的音色，本地删除应当成功"""
        v = Voice.objects.create(name='m', voice_id='rm_4', owner=user_profile,
                                 visibility='private')
        with patch(REMOVE + '.delete_voice', side_effect=AliyunNotFound()):
            resp = auth_client.post('/api/create/character/voice/remove/', {'voice': v.id})
        assert resp.status_code == 200
        assert not Voice.objects.filter(id=v.id).exists()

    def test_restricted_race_returns_400_not_500(self, auth_client, user_profile):
        """预检查与真正删除之间的竞态：这中间新建了一个用它的角色 → 被 RESTRICT 拒绝

        不补这层兜底，`RestrictedError` 会漏到最外面变成 500（spec §7 明确不许）。
        """
        v = Voice.objects.create(name='m', voice_id='rm_5', owner=user_profile,
                                 visibility='private')
        with patch(REMOVE + '.delete_voice'), \
             patch.object(Voice, 'delete', side_effect=RestrictedError('still referenced')):
            resp = auth_client.post('/api/create/character/voice/remove/', {'voice': v.id})
        assert resp.status_code == 400
        assert '角色' in resp.json()['message']
```

- [ ] **Step 2: 跑测试确认失败** → URL 未注册。

- [ ] **Step 3: 实现**

`remove.py` 的顺序与分档 —— **严格按 spec §7，只有两档，没有"上游拒绝 → 400"这一档**：

1. 可见性守卫（与 create/update/sample 同一条）→ 别人的 / 不存在 → **404**，message 与"不存在"逐字相同；
2. 引用检查 → `Character.objects.filter(voice=voice).exists()` → **400** + 「该音色正被 N 个角色使用，无法删除」（本地就能判定，不白跑一趟上游）；
3. 调阿里云 `delete_voice`（5 秒超时）：
   - 返回**「不存在」** → **视为删除成功**，继续删本地行（识别方式以 Task 1 Step 5 实测到的返回形状为准，不靠猜）；
   - **其余任何失败或超时** → **503** + **保留本地行**（保住 `voice_id` 以便重试）。⚠️ **上游拒绝不是用户的错，不能归 400** —— 这条上一版写得含糊（"明确拒绝 → 400"），按 spec 写死；
4. 删本地行时补一层 `except RestrictedError` → **400** + 同一句提示：预检查与真正删除之间存在竞态（这中间新建了一个用它的角色），不补就会把 `RestrictedError` 漏成 500（spec §7 明确不许）。

- [ ] **Step 4: 跑测试确认通过** → 全绿。

- [ ] **Step 5: 提交**

```bash
git add backend/web/views/create/character/voice/remove.py backend/web/urls.py backend/web/tests/test_voice_clone.py
git commit -m "feat(voice): 删除音色时同步删阿里云侧，失败则保留行"
```

---

### Task 6: `clean_dirty_characters` 的 DEBUG 闸 + 删掉未接线原型

**Files:**
- Modify: `backend/web/management/commands/clean_dirty_characters.py`
- Delete: `backend/web/views/create/character/voice/custom/`（三个文件）
- Test: `backend/web/tests/test_voice_clone.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
class TestCleanCommandGuard:
    def test_all_refused_when_not_debug(self, settings):
        """生产（DEBUG=False）下拒绝执行 --all —— 它现在能删真实用户数据"""
        settings.DEBUG = False
        with pytest.raises(CommandError) as e:
            call_command('clean_dirty_characters', '--all')
        assert '生产' in str(e.value) or 'DEBUG' in str(e.value)

    def test_all_allowed_when_debug(self, settings, db):
        settings.DEBUG = True
        call_command('clean_dirty_characters', '--all')      # 不抛
```

- [ ] **Step 2: 跑测试确认失败** → 现在生产下也会照跑（不抛）。

- [ ] **Step 3: 实现 + 删原型**

在 `handle()` 开头加：

```python
        if clean_all and not settings.DEBUG:
            raise CommandError(
                '--all 会删除真实用户数据（音色 / 用户），已禁止在生产执行；'
                '如需清理测试残留请在 DEBUG=True 下运行')
```

删掉 `backend/web/views/create/character/voice/custom/`（`create_voice.py` / `list_voice.py` / `delete_voice.py` / `__init__.py`）——它们的逻辑已被 Task 3/4/5 的正式实现吸收，仓库里不再需要未接线的原型（`grep -rn "voice.custom" backend/` 应无输出后再删）。

- [ ] **Step 4: 跑测试确认通过** → 全绿。

- [ ] **Step 5: 提交**

```bash
git add backend/web/management/commands/clean_dirty_characters.py backend/web/views/create/character/voice/custom backend/web/tests/test_voice_clone.py
git commit -m "feat(voice): clean --all 在生产拒绝执行；删除未接线的声音复刻原型"
```

---

### Task 7: 前端 —— 我的音色（上传 / 状态 / 删除）

**Files:**
- Create: `frontend/src/views/create/character/components/MyVoiceManager.vue`
- Create: `frontend/src/views/create/character/components/__tests__/MyVoiceManager.test.js`
- Modify: `frontend/src/views/create/character/CreateCharacter.vue`（引入）
- Modify: `frontend/src/views/create/character/UpdateCharacter.vue`（引入）

**Interfaces:**
- Consumes: `POST /api/create/character/voice/clone/`（multipart）、`POST /api/create/character/voice/remove/`、`GET /api/create/character/voice/get_list/`（已有 `is_mine` / `status`）

- [ ] **Step 1: 写失败测试**

在 `MyVoiceManager.test.js` 里覆盖四条（沿用仓库既有的"手工 `createApp` + `h` + 查 DOM"写法 —— **本仓库没有 `@vue/test-utils`**）：

```js
  it('渲染我的音色与状态标注', ...)      // is_mine=true 的行 + 「审核中」/「审核未通过」
  it('超过 8MB 的文件在前端就被拦住，不发请求', ...)
  it('未勾选授权声明时拦住提交，不发请求', ...)
  it('提交调用 clone 接口（multipart 含 file/name/profile/consent）', ...)
  it('删除按钮调用 remove 接口', ...)
  it('隐私说明不过度承诺：断言不含“全链路”与“已删除”这两个片段', ...)
  // ⚠️ 别写成 not.toContain('删除') —— 被批准的文案本身就含"我们会立即删除"，
  //    那样写必然失败，而"让它通过"的最短路径是把文案改弱，正好把 spec §8 的要求搞坏。
  //    断言只钉这两个片段：它们与必备文案不冲突（spec 风险 12）。
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npm run test:unit -- src/views/create/character/components/__tests__/MyVoiceManager.test.js`

- [ ] **Step 3: 实现**

组件职责（保持精简）：
- 「创建我的音色」折叠区：文件选择（`accept=".mp3,.wav,.m4a"`）+ 名称输入 + 可选描述 + **授权声明勾选框** + 提交按钮
- **授权声明与隐私文案（spec §6.2.1 / §8，是合规要求、不是可选项）**：
  - 勾选框文字：「我确认这是**本人声音**，或已获得声音权利人授权」
  - 必须附一句隐私说明，措辞写成**「样本会被提交给语音合成服务方用于复刻，复刻完成后我们会立即删除」** —— ⚠️ **不能写成"全链路已删除"**：实测阿里云侧仍留有原始样本（`query_voice` 能返回 `resource_link`，见 spec 风险 12）
  - **未勾选时前端拦住提交**（Task 3 后端还有一道，两道都要有）
- 前端校验：大小 >8MB、后缀不在白名单、名称为空、**未勾选授权** → 就地报错，**不发请求**
- 提交：`FormData` 走 `api.post('/api/create/character/voice/clone/', fd)`，`fd` 里带 `consent: 'true'`
- 「我的音色」列表：名称 + 状态徽章（`deploying` → 审核中、`rejected` → 审核未通过、`ready` → 可用）+ 删除按钮（`confirm` 后调 remove）
- 有 `deploying` 行时每 30 秒刷新一次列表，全部落地后停止（复用 `useDocumentPolling` 的写法，但不引入新依赖）

在 `CreateCharacter.vue` / `UpdateCharacter.vue` 的 `<Voice>` 之后各加一行 `<MyVoiceManager ref="my-voice-ref" :voices="voices"/>`（父组件已有 `voices` 数据与刷新入口；创建/删除后需重新拉取音色列表，最简做法是把 `getCharacterData` / 首次拉取逻辑抽成一个可复用的 `refreshVoices()`）。

- [ ] **Step 4: 跑测试确认通过** → `npm run test:unit` 全绿。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/create/character/
git commit -m "feat(voice): 我的音色 —— 上传复刻样本、查看状态、删除"
```

---

### Task 8: 全量验证与提 PR（门 3 入口）

- [ ] **Step 1: 后端全量** → `pytest web/tests/ -v` 全绿（基线 274 + 本批新增）
- [ ] **Step 2: 前端全量** → `npm run test:unit` 全绿（基线 156 + 本批新增）
- [ ] **Step 3: 构建** → `VITE_PLATFORM=docker npm run build` 成功
- [ ] **Step 4: 提 PR**（标题 `feat(voice): 复刻接线 —— 用户自建音色`），正文写明：做了什么 / 证据 / **部署与验收步骤** / **本批新增的对阿里云与 OSS 的真实账号操作**（Task 1 的实测与清理结论）
- [ ] **Step 5: 把 PR 链接交用户走门 3**

---

## Self-Review

**Spec 覆盖**
- §5 接口：`clone` → Task 3；`remove` → Task 5。
- §6.2 复刻流程：OSS 上传（对象级 private）→ Task 2；`create_voice` 与失败分档 → Task 3；状态刷新（**Beat 而非长轮询**）→ Task 4；删除同步阿里云 → Task 5；配额 → Task 3（每用户 5）+ Task 4（全平台水位 800）。
- §7 错误表：样本/参数 → 400（Task 3）、上游不可用 → 503（Task 3/5）、删除被引用 → 400（Task 5）。
- §9 D 批 11 条：D1/D2/D3/D4 → Task 3；D5 → Task 4；D6 → Task 3；D7/D8/D9 → Task 5；D10 → Task 3；D11 → Task 2/3。
- §10 D 批验收：样本清理可查（Task 2/3 的 mock 断言 + 门 4 的 OSS 列表核对）、删除后阿里云侧同步（Task 5 + 门 4 的 `list_voice` 核对）。
- §11 风险 5（未存 `target_model`）、9（长期 `deploying`）、10（孤儿音色）、12（样本在阿里云侧留存）、14（桶是 public-read → 对象级 private）→ 分别在 Task 3/4 的注释与实现里落实；风险 11（`clean_dirty_characters`）→ Task 6。
- §13 分批表 D 行：`clean_dirty_characters` 的 DEBUG 闸 → Task 6；删 `voice/custom/` 原型 → Task 6。

**Type 一致性**：`upload_private(bytes, suffix) -> str` / `presign_get(key, minutes=5) -> str` / `delete_object_quietly(key) -> None`（Task 2 定义，Task 3 使用）；`create_voice(url, prefix) -> str` 抛 `AliyunRejected` / `AliyunUnavailable`（Task 3 定义与使用）；`query_status(voice_id) -> str`（Task 4 定义与使用）；`VOICE_QUOTA_PER_USER` / `user_voice_count(profile)`（Task 3 定义与使用）。

**未决/转二期**：公开共享、举报下架、音色分类分页、阿里云音色探活。**本批不做**（spec §2.2）。

**开工前必须过的两道**：① Task 1 的真实账号往返（含清理）—— 它决定 Task 3/4 的参数与节奏；② 门 2 批准（Task 1 会真的在你的账号里创建/删除音色与对象，这一点必须在批准时知情）。
