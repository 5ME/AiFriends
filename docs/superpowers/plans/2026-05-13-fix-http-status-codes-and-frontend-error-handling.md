# Fix HTTP Status Codes and Frontend Error Handling

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 14 wrong HTTP status codes in backend views and update frontend error handling so the app correctly surfaces API errors to users instead of silently swallowing them.

**Architecture:** Backend changes are mechanical: replace default-200 error responses with the semantically correct 400/401/404/409 status codes. Frontend changes have two layers: (1) axios interceptor gets a whitelist to skip 401→token-refresh for login/register endpoints, (2) callers that already have error UI (LoginIndex, RegisterIndex, CreateCharacter, UpdateCharacter, ProfileIndex) update their catch blocks to read from `e.response.data.message`. For listing/display components that currently `console.log(e)` silently, add minimal error feedback via a local `errorMessage` ref.

**Key design rule:** After backend returns proper 4xx, the axios success interceptor only sees 2xx. So components no longer need `if (data.message === 'success')` — 200 means success. All errors go through catch. This simplifies the caller code.

**Tech Stack:** Django 6.0 + DRF, Vue 3 + axios + Pinia

---

### Task 1: Fix backend status codes — auth views

**Files:**
- Modify: `backend/web/views/user/account/login.py`
- Modify: `backend/web/views/user/account/register.py`

- [ ] **Step 1: Fix login.py — wrong credentials returns 401**

Change line 34 from:
```python
                return Response({'message': '用户名或密码错误'},
                                status=status.HTTP_200_OK)
```
to:
```python
                return Response({'message': '用户名或密码错误'},
                                status=status.HTTP_401_UNAUTHORIZED)
```

- [ ] **Step 2: Fix register.py — empty fields returns 400**

Change line 16 from:
```python
                return Response({'message': '用户名和密码不能为空'})
```
to:
```python
                return Response({'message': '用户名和密码不能为空'},
                                status=status.HTTP_400_BAD_REQUEST)
```

- [ ] **Step 3: Fix register.py — duplicate username returns 409**

Change line 18 from:
```python
                return Response({'message': '此用户名已被占用'})
```
to:
```python
                return Response({'message': '此用户名已被占用'},
                                status=status.HTTP_409_CONFLICT)
```

- [ ] **Step 4: Verify backend imports OK**

```bash
cd backend && conda run -n py312 python -c "from web.views.user.account import login, register; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/web/views/user/account/login.py backend/web/views/user/account/register.py
git commit -m "fix: correct HTTP status codes in auth views (401/400/409)

- Login wrong password: 200 -> 401
- Register empty fields: 200 -> 400
- Register duplicate username: 200 -> 409

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: Fix backend status codes — profile and chat views

**Files:**
- Modify: `backend/web/views/user/profile/update.py`
- Modify: `backend/web/views/friend/message/chat/chat.py`

- [ ] **Step 1: Fix update.py — empty username returns 400**

Change line 24 from:
```python
                return Response({'message': '用户名不能为空'})
```
to:
```python
                return Response({'message': '用户名不能为空'},
                                status=status.HTTP_400_BAD_REQUEST)
```

- [ ] **Step 2: Fix update.py — empty profile returns 400**

Change line 26 from:
```python
                return Response({'message': '简介不能为空'})
```
to:
```python
                return Response({'message': '简介不能为空'},
                                status=status.HTTP_400_BAD_REQUEST)
```

- [ ] **Step 3: Fix update.py — duplicate username returns 409**

Change line 28 from:
```python
                return Response({'message': '此用户名已存在'})
```
to:
```python
                return Response({'message': '此用户名已存在'},
                                status=status.HTTP_409_CONFLICT)
```

- [ ] **Step 4: Fix chat.py — empty message returns 400**

Change line 105 from:
```python
                return Response({"message": "消息不能为空"})
```
to:
```python
                return Response({"message": "消息不能为空"},
                                status=status.HTTP_400_BAD_REQUEST)
```

- [ ] **Step 5: Fix chat.py — friend not found returns 404**

Change line 108 from:
```python
                return Response({"message": "好友关系不存在"})
```
to:
```python
                return Response({"message": "好友关系不存在"},
                                status=status.HTTP_404_NOT_FOUND)
```

- [ ] **Step 6: Verify imports**

```bash
cd backend && conda run -n py312 python -c "from web.views.user.profile import update; from web.views.friend.message.chat import chat; print('OK')"
```
Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add backend/web/views/user/profile/update.py backend/web/views/friend/message/chat/chat.py
git commit -m "fix: correct HTTP status codes in profile and chat views (400/404/409)

- Profile empty fields: 200 -> 400
- Profile duplicate username: 200 -> 409
- Chat empty message: 200 -> 400
- Chat friend not found: 200 -> 404

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: Fix backend status codes — character views

**Files:**
- Modify: `backend/web/views/create/character/create.py`
- Modify: `backend/web/views/create/character/update.py`

- [ ] **Step 1: Fix create.py — empty name returns 400**

Change line 24 from:
```python
                return Response({'message': '角色名称不能为空'})
```
to:
```python
                return Response({'message': '角色名称不能为空'},
                                status=status.HTTP_400_BAD_REQUEST)
```

- [ ] **Step 2: Fix create.py — empty profile returns 400**

Change line 26 from:
```python
                return Response({'message': '角色信息不能为空'})
```
to:
```python
                return Response({'message': '角色信息不能为空'},
                                status=status.HTTP_400_BAD_REQUEST)
```

- [ ] **Step 3: Fix create.py — no photo returns 400**

Change line 28 from:
```python
                return Response({'message': '角色头像不能为空'})
```
to:
```python
                return Response({'message': '角色头像不能为空'},
                                status=status.HTTP_400_BAD_REQUEST)
```

- [ ] **Step 4: Fix create.py — no background returns 400**

Change line 30 from:
```python
                return Response({'message': '对话背景不能为空'})
```
to:
```python
                return Response({'message': '对话背景不能为空'},
                                status=status.HTTP_400_BAD_REQUEST)
```

- [ ] **Step 5: Fix update.py — empty name returns 400**

Change line 26 from:
```python
                return Response({'message': '角色名称不能为空'})
```
to:
```python
                return Response({'message': '角色名称不能为空'},
                                status=status.HTTP_400_BAD_REQUEST)
```

- [ ] **Step 6: Fix update.py — empty profile returns 400**

Change line 28 from:
```python
                return Response({'message': '角色信息不能为空'})
```
to:
```python
                return Response({'message': '角色信息不能为空'},
                                status=status.HTTP_400_BAD_REQUEST)
```

- [ ] **Step 7: Verify imports**

```bash
cd backend && conda run -n py312 python -c "from web.views.create.character import create, update; print('OK')"
```
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add backend/web/views/create/character/create.py backend/web/views/create/character/update.py
git commit -m "fix: correct HTTP status codes in character views (400)

All validation errors in create/update character: 200 -> 400

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: Fix frontend axios interceptor — add 401 whitelist

**Files:**
- Modify: `frontend/src/js/http/api.js`

- [ ] **Step 1: Read current api.js**

Read the response interceptor section (lines 67-128).

- [ ] **Step 2: Add login/register whitelist before the 401 check**

In the response error interceptor, before the `if (error.response?.status === 401 ...)` block (currently line 81), add:

```javascript
// 登录/注册接口的 401 表示"凭据错误"，不应触发 token 刷新
const AUTH_WHITELIST = ['/api/user/account/login/', '/api/user/account/register/']
const isAuthEndpoint = AUTH_WHITELIST.some(path => error.config?.url?.includes(path))
```

Then wrap the existing 401 logic (lines 81-122) with an `if (!isAuthEndpoint)` check:

```javascript
      // 检查是否是 401 未授权错误，且该请求未被重试过（避免无限循环）
      // 登录/注册接口的 401 是"凭据错误"，跳过 token 刷新
      if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
        // ... 原有 token 刷新逻辑保持不变 ...
      }
```

The existing logic between `if (error.response?.status === 401 ...)` and the closing `}` before `return Promise.reject(error)` stays unchanged — we only add `&& !isAuthEndpoint` to the condition.

- [ ] **Step 3: Verify the file has no syntax errors**

```bash
cd frontend && npx eslint src/js/http/api.js --format=compact 2>&1 || node -e "const fs = require('fs'); eval(fs.readFileSync('src/js/http/api.js', 'utf8').replace(/import /g, '// import ')); console.log('Syntax OK')"
```
Expected: No syntax errors reported

- [ ] **Step 4: Commit**

```bash
git add frontend/src/js/http/api.js
git commit -m "fix: add auth endpoint whitelist to skip 401 token refresh for login/register

Login/register 401 errors represent wrong credentials, not expired tokens.
Without this, the interceptor would attempt a token refresh on login failure.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: Fix frontend — auth page error handling (LoginIndex + RegisterIndex)

**Files:**
- Modify: `frontend/src/views/user/account/LoginIndex.vue`
- Modify: `frontend/src/views/user/account/RegisterIndex.vue`

- [ ] **Step 1: Fix LoginIndex.vue**

The current code (lines 24-42) checks `data.message === 'success'`. After backend fixes, 200 always = success. Rewrite the try/catch:

```javascript
    try {
      const response = await api.post('/api/user/account/login/', {
        'username': username.value,
        'password': password.value
      })
      const data = response.data
      // 200 一定是登录成功
      user.setAccessToken(data.access_token)
      user.setUserInfo(data)
      await router.push({
        name: 'homepage-index'
      })
    } catch (e) {
      // 401/400/500 统一在此处理
      errorMessage.value = e.response?.data?.message || '网络异常'
    }
```

Also remove the debug `console.log` on line 17:
```javascript
  console.log("handle login request...")
```
Delete that line.

- [ ] **Step 2: Fix RegisterIndex.vue**

Read `frontend/src/views/user/account/RegisterIndex.vue` first (same pattern as LoginIndex). Apply the same transformation:

```javascript
    try {
      const response = await api.post('/api/user/account/register/', {
        'username': username.value,
        'password': password.value
      })
      const data = response.data
      // 200 一定是注册成功
      user.setAccessToken(data.access_token)
      user.setUserInfo(data)
      await router.push({
        name: 'homepage-index'
      })
    } catch (e) {
      // 400/409/500 统一在此处理
      errorMessage.value = e.response?.data?.message || '网络异常'
    }
```

- [ ] **Step 3: Verify no obvious issues in both files**

Read both files to confirm edits are correct.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/user/account/LoginIndex.vue frontend/src/views/user/account/RegisterIndex.vue
git commit -m "fix: update auth page error handling for proper HTTP status codes

- Remove 'data.message === success' check (200 now guarantees success)
- Read error message from catch block via e.response.data.message
- Remove debug console.log from LoginIndex

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: Fix frontend — character CRUD error handling (CreateCharacter + UpdateCharacter)

**Files:**
- Modify: `frontend/src/views/create/character/CreateCharacter.vue`
- Modify: `frontend/src/views/create/character/UpdateCharacter.vue`

These two components have more complex logic — they call multiple APIs (voice list get + character create/update) and already have `errorMessage` UI.

- [ ] **Step 1: Fix CreateCharacter.vue — voice list fetch**

Read the file first. Find the voice list fetch (GET `/api/create/character/voice/get_list/`). Change from:

```javascript
    const response = await api.get('/api/create/character/voice/get_list/')
    const data = response.data
    if (data.message === "success") {
      voices.value = data.voices
    }
  } catch (e) {
    console.log(e)
  }
```

to:

```javascript
    const response = await api.get('/api/create/character/voice/get_list/')
    voices.value = response.data.voices
  } catch (e) {
    console.log(e)
    // 音色列表加载失败不影响创建流程，仅静默
  }
```

- [ ] **Step 2: Fix CreateCharacter.vue — character creation**

Change the handleCreate function from:

```javascript
    const response = await api.post('/api/create/character/create/', formData)
    const data = response.data
    if (data.message === 'success') {
      await router.push({name: 'user-space-index'})
    } else {
      errorMessage.value = data.message
    }
  } catch (e) {
    console.log(e)
  }
```

to:

```javascript
    const response = await api.post('/api/create/character/create/', formData)
    // 200 = 创建成功
    await router.push({name: 'user-space-index'})
  } catch (e) {
    errorMessage.value = e.response?.data?.message || '网络异常'
  }
```

- [ ] **Step 3: Fix UpdateCharacter.vue — character data fetch**

Change the character data fetch (GET `/api/create/character/get_single/`) from:

```javascript
    const response = await api.get('/api/create/character/get_single/', {params})
    const data = response.data
    if (data.message === 'success') {
      // populate form fields
    }
  } catch (e) {
    console.log(e)
  }
```

to:

```javascript
    const response = await api.get('/api/create/character/get_single/', {params})
    const data = response.data
    // 200 = 获取成功
    // populate form fields... (keep existing population logic)
  } catch (e) {
    console.log(e)
    // 获取失败静默，表单保持空白
  }
```

- [ ] **Step 4: Fix UpdateCharacter.vue — character update**

Change the handleUpdate function from:

```javascript
    const response = await api.post('/api/create/character/update/', formData)
    const data = response.data
    if (data.message === 'success') {
      await router.push({name: 'user-space-index'})
    } else {
      errorMessage.value = data.message
    }
  } catch (e) {
    console.log(e)
  }
```

to:

```javascript
    const response = await api.post('/api/create/character/update/', formData)
    // 200 = 更新成功
    await router.push({name: 'user-space-index'})
  } catch (e) {
    errorMessage.value = e.response?.data?.message || '网络异常'
  }
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/create/character/CreateCharacter.vue frontend/src/views/create/character/UpdateCharacter.vue
git commit -m "fix: update character CRUD error handling for proper HTTP status codes

- Voice list fetch: remove success check (200 = success)
- Character create/update: read error from catch block
- Character data fetch: remove success check

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: Fix frontend — profile update error handling (ProfileIndex)

**Files:**
- Modify: `frontend/src/views/user/profile/ProfileIndex.vue`

- [ ] **Step 1: Fix the handleUpdate function**

Read the file first. Change the POST handler from:

```javascript
    const response = await api.post('/api/user/profile/update/', formData)
    const data = response.data
    if (data.message === 'success') {
      // update store
    } else {
      errorMessage.value = data.message
    }
  } catch (err) {
    console.log(err)
  }
```

to:

```javascript
    const response = await api.post('/api/user/profile/update/', formData)
    const data = response.data
    // 200 = 更新成功
    // update store... (keep existing logic)
  } catch (err) {
    errorMessage.value = err.response?.data?.message || '网络异常'
  }
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/user/profile/ProfileIndex.vue
git commit -m "fix: update profile page error handling for proper HTTP status codes

Read error message from catch block instead of 200 body check.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 8: Fix frontend — remaining components (console.log → minimal feedback)

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/views/homepage/HomepageIndex.vue`
- Modify: `frontend/src/views/friend/FriendIndex.vue`
- Modify: `frontend/src/views/user/space/SpaceIndex.vue`
- Modify: `frontend/src/components/character/Character.vue`
- Modify: `frontend/src/components/character/CharacterDetail.vue`
- Modify: `frontend/src/components/character/chat_field/chat_history/ChatHistory.vue`
- Modify: `frontend/src/components/character/chat_field/input_field/Microphone.vue`
- Modify: `frontend/src/components/navbar/UserMenu.vue`

These components currently have `catch (e) { console.log(e) }` with no user-facing error feedback. For each, we make two changes:

1. Add a `const errorMessage = ref('')` (if not already present)
2. In catch blocks, replace `console.log(e)` with `errorMessage.value = e.response?.data?.message || '请求失败'`
3. Add `<p v-if="errorMessage" class="text-sm text-red-600">{{ errorMessage }}</p>` in the template at an appropriate position
4. Remove the `if (data.message === 'success')` check where it exists — after backend changes, 200 means success

**Exception — listing components** (HomepageIndex, FriendIndex, SpaceIndex, ChatHistory): These are infinite-scroll paginated lists. A load error should not break the whole page — instead show a brief toast-style error and continue. Use a simpler approach: keep the `console.log(e)` but also set a local `loadError` ref that shows a small banner at the top of the list.

**Exception — Microphone.vue and UserMenu.vue**: Audio recording failure and logout failure are non-critical. Keep the `console.log` but add a comment noting the intentional silence.

**Exception — Character.vue and CharacterDetail.vue**: These have multiple API calls. Each call's catch currently `console.log(e)`. For remove friend / add friend failures, add error feedback. For get_or_create failure (which opens chat), show error because the user explicitly clicked.

- [ ] **Step 1: Fix App.vue — user info fetch**

Read `frontend/src/App.vue`. The `getUserInfo` call is critical — if it fails, the app has no user state. Change:

```javascript
    const response = await api.get('/api/user/account/get_user_info/')
    const data = response.data
    if (data.message === 'success') {
      user.setUserInfo(data)
    }
  } catch (e) {
    console.log(e)
  } finally {
    hasPulledUserInfo.value = true
    // redirect logic...
  }
```

to:

```javascript
    const response = await api.get('/api/user/account/get_user_info/')
    // 200 = 获取成功
    user.setUserInfo(response.data)
  } catch (e) {
    console.log(e)
    // 静默失败 — finally 块会将用户重定向到登录页
  } finally {
    hasPulledUserInfo.value = true
    // redirect logic... (keep existing)
  }
```

- [ ] **Step 2: Fix Character.vue — friend add/remove operations**

Read the file. This component has 3 API calls: remove character, get_or_create friend, remove friend. For `get_or_create` (the most user-facing action — clicking "开始聊天"), add error display:

Add near other refs:
```javascript
const friendErrorMessage = ref('')
```

In the handleAddFriend function's catch block, change:
```javascript
  } catch (e) {
    console.log(e)
  }
```
to:
```javascript
  } catch (e) {
    friendErrorMessage.value = e.response?.data?.message || '操作失败'
  }
```

In the template, add after the existing button area:
```html
<p v-if="friendErrorMessage" class="text-sm text-red-600 mt-2">{{ friendErrorMessage }}</p>
```

For the remove character and remove friend handlers, keep catch blocks silent (these are destructive actions where the UI updates optimistically).

- [ ] **Step 3: Fix CharacterDetail.vue — friend check and add**

Read the file. Same pattern as Character.vue. Add error feedback for the get_or_create call. The is_friend check can stay silent (it runs on modal open).

- [ ] **Step 4: Fix HomepageIndex.vue, FriendIndex.vue, SpaceIndex.vue, ChatHistory.vue — paginated lists**

For each paginated list view, add a simple error indicator:

Add ref:
```javascript
const loadError = ref('')
```

In catch block change:
```javascript
  } catch (e) {
    console.log(e)
  }
```
to:
```javascript
  } catch (e) {
    console.log(e)
    loadError.value = '加载失败，请稍后重试'
  }
```

In template, add before the list:
```html
<p v-if="loadError" class="text-center text-sm text-red-500 py-4">{{ loadError }}</p>
```

Also remove the `if (data.message === 'success')` check — 200 = success now.

- [ ] **Step 5: Fix Microphone.vue and UserMenu.vue — intentional silence**

No code changes. Add a comment above each catch explaining the silence is intentional (non-critical operations).

- [ ] **Step 6: Commit all remaining component fixes**

```bash
git add frontend/src/App.vue frontend/src/components/character/Character.vue frontend/src/components/character/CharacterDetail.vue frontend/src/views/homepage/HomepageIndex.vue frontend/src/views/friend/FriendIndex.vue frontend/src/views/user/space/SpaceIndex.vue frontend/src/components/character/chat_field/chat_history/ChatHistory.vue
git commit -m "fix: add error feedback to remaining components, remove success checks

Replace silent console.log catches with user-facing error messages
in character interactions, paginated lists, and user info fetch.
Remove redundant data.message checks (200 now guarantees success).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 9: End-to-end verification

- [ ] **Step 1: Run Django system check**

```bash
cd backend && conda run -n py312 python manage.py check
```
Expected: "System check identified no issues (0 silenced)."

- [ ] **Step 2: Verify all backend views import correctly**

```bash
cd backend && conda run -n py312 python -c "
import django; import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()
from web.views.user.account import login, register
from web.views.user.profile import update
from web.views.create.character import create, update as char_update
from web.views.friend.message.chat import chat
print('All imports OK')
"
```
Expected: `All imports OK`

- [ ] **Step 3: Verify no 200 status on error responses**

```bash
grep -rn "status=status.HTTP_200_OK" backend/web/views/
```
Expected: search results may show valid 200 usages (success paths). Key check: login.py should no longer have 200 on "用户名或密码错误".

- [ ] **Step 4: Verify frontend builds**

```bash
cd frontend && npm run build
```
Expected: Build completes without errors.

- [ ] **Step 5: Manual test checklist**

Start dev server and test:
```
□ 登录 — 错误密码 → 显示"用户名或密码错误"（红色提示，不跳转）
□ 登录 — 正确密码 → 正常跳转首页
□ 注册 — 空字段 → 显示"用户名和密码不能为空"
□ 注册 — 重复用户名 → 显示"此用户名已被占用"
□ 首页 — 正常加载角色列表
□ 角色详情 — 点击"开始聊天"正常进入
□ 好友列表 — 正常加载
□ 聊天 — 发送消息正常
□ 创建角色 — 空名称 → 显示"角色名称不能为空"
□ 更新角色 — 正常
□ 用户资料 — 空名称 → 显示"用户名不能为空"
```

- [ ] **Step 6: Commit any final tweaks**

```bash
git status
```
If clean, done. If any fixes from manual testing, commit them.
