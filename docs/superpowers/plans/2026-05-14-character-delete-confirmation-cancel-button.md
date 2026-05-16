# 角色删除确认弹窗 + 创建/编辑取消按钮 — 实施计划

> **Design doc:** `docs/superpowers/specs/2026-05-14-character-delete-confirmation-cancel-button.md`

**Goal:** 角色删除前弹窗确认，展示实时好友数；创建/编辑页加取消按钮。

**Architecture:** 后端 2 处改动（get_list 加 friend_count，get_count 新端点），前端 3 处改动。Character.vue 删除流程改为先查实时好友数再弹窗，接口异常时降级用列表中的缓存值。

**分支:** `feature/gqyin/character-delete-confirmation`

---

### Task 1: 后端 — get_list.py 增加 friend_count

**Files:** `backend/web/views/create/character/get_list.py`

- [x] **Step 1: 添加 import**
- [x] **Step 2: 在角色循环中添加 friend_count 查询**
- [x] **Step 3: 在响应 dict 中添加 friend_count 字段**
- [x] **Step 4: 验证 import**
- [x] **Step 5: 提交** `0e6c813` feat: add friend_count to character list response

---

### Task 2: 后端 — 新增 get_count 端点

**Files:**
- Create: `backend/web/views/friend/get_count.py`
- Modify: `backend/web/urls.py`

- [ ] **Step 1: 创建 get_count.py**

新建文件，内容参考 `is_friend.py` 的模式：

```python
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.friend import Friend

logger = logging.getLogger(__name__)


class FriendGetCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            character_id = request.query_params.get('character_id')
            friend_count = Friend.objects.filter(character_id=character_id).count()
            return Response({
                'message': 'success',
                'friend_count': friend_count,
            })
        except Exception as e:
            logger.exception('获取好友数异常: %s', e)
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 2: 注册路由**

在 `backend/web/urls.py` 中添加 import 和路由：
```python
from web.views.friend.get_count import FriendGetCountView
# ...
path('api/friend/get_count/', FriendGetCountView.as_view()),
```

- [ ] **Step 3: 验证 import**

```bash
cd backend && conda run -n py312 python -c "import django; import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings'); django.setup(); from web.views.friend.get_count import FriendGetCountView; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: 提交**

```bash
git add backend/web/views/friend/get_count.py backend/web/urls.py
git commit -m "feat: add friend get_count endpoint for real-time deletion warning

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: 前端 — Character.vue 删除确认弹窗（含实时查询）

**Files:** `frontend/src/components/character/Character.vue`

- [x] **Step 1: 添加 deleteConfirmModalRef**

- [ ] **Step 2: handleRemoveCharacter 改为先查实时好友数再弹窗**

```typescript
const deleteFriendCount = ref(0)

async function handleRemoveCharacter() {
  try {
    const response = await api.get('/api/friend/get_count/', {
      params: { character_id: props.character.id }
    })
    deleteFriendCount.value = response.data.friend_count
  } catch (e) {
    // 接口异常时降级用列表中的缓存值
    deleteFriendCount.value = props.character.friend_count || 0
  }
  deleteConfirmModalRef.value.showModal()
}
```

弹窗中 `v-if` 判断使用 `deleteFriendCount` 而非 `character.friend_count`。

- [ ] **Step 3: confirmRemoveCharacter 函数**（已完成）

- [ ] **Step 4: 弹窗模板**（已完成，需将 `character.friend_count` 替换为 `deleteFriendCount`）

- [ ] **Step 5: 验证 TypeScript 编译**（项目未安装 vue-tsc，跳过）

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/character/Character.vue
git commit -m "feat: query real-time friend count before showing delete confirmation

Fall back to cached friend_count on request failure.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: 前端 — CreateCharacter.vue 取消按钮

**Files:** `frontend/src/views/create/character/CreateCharacter.vue`

- [x] **已完成** `f6559f6` feat: add cancel button to character creation form

---

### Task 5: 前端 — UpdateCharacter.vue 取消按钮

**Files:** `frontend/src/views/create/character/UpdateCharacter.vue`

- [x] **已完成** `7307768` feat: add cancel button to character update form

---

### Task 6: 最终验证

- [ ] **Step 1: Django system check**

```bash
cd backend && conda run -n py312 python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 2: 确认 git 状态清洁**

```bash
git status
```
Expected: 工作区无修改

- [ ] **Step 3: 手工验证清单**

1. 删除有好友的角色 → 弹窗显示实时好友数 → 取消 → 角色未删除
2. 删除有好友的角色 → 弹窗 → 确认 → 角色从列表移除
3. 删除无好友的角色 → 弹窗不显示好友相关行 → 确认 → 角色删除
4. 创建角色页 → 取消 → 返回上一页
5. 编辑角色页 → 取消 → 返回上一页，数据未保存
