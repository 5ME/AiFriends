# 角色删除确认弹窗 + 创建/编辑取消按钮

> 设计日期：2026-05-14 | 状态：待实施

## 背景

当前角色管理流程存在两个 UX 缺陷：

1. **角色删除无确认**：用户空间中删除角色一键即删，无任何确认提示。但通过外键级联，角色删除会导致所有好友关系（`Friend`）及聊天记录（`Message`）被永久清除。相比之下，"解除好友"流程有完整确认弹窗 —— 删除角色（后果更严重）反而不需要确认。

2. **创建/编辑表单无取消按钮**：`CreateCharacter.vue` 和 `UpdateCharacter.vue` 只有提交按钮，用户无法便捷返回。

## 目标

- 角色删除前弹出确认框，展示实时好友数量，明确警告数据不可恢复
- 创建和编辑角色页面增加取消按钮
- 与现有"解除好友"弹窗保持一致的交互模式和视觉风格

## 详细设计

### 改动 1 — get_list.py：角色列表返回好友数

**文件：** `backend/web/views/create/character/get_list.py`

在角色列表序列化中增加 `friend_count` 字段，用于卡片展示（非实时，仅作参考）。

```python
from web.models.friend import Friend  # 新增 import

# 在 for character in character_list: 循环中添加
friend_count = Friend.objects.filter(character_id=character.id).count()
characters.append({
    ...
    'friend_count': friend_count,  # 新增
})
```

### 改动 2 — get_count.py：实时查询好友数端点（新增）

**文件：** `backend/web/views/friend/get_count.py`（新文件）

用于删除前获取最新好友数，避免因页面停留时间过长导致好友数过期。

```
GET /api/friend/get_count/?character_id=X

Response:
{
    "message": "success",
    "friend_count": 3
}
```

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

**路由注册：** `backend/web/urls.py`
```python
from web.views.friend.get_count import FriendGetCountView
# ...
path('api/friend/get_count/', FriendGetCountView.as_view()),
```

### 改动 3 — Character.vue：删除确认弹窗（含实时查询）

**文件：** `frontend/src/components/character/Character.vue`

**流程变化：**

```
用户点击删除按钮
  → handleRemoveCharacter()
  → 调 GET /api/friend/get_count/ 获取实时好友数
  → 成功：用实时 friend_count 打开弹窗
  → 失败：降级用 props.character.friend_count 打开弹窗
用户点确认
  → confirmRemoveCharacter()
  → POST /api/character/remove/ 执行删除
```

弹窗文案（只有一种，好友数按实时值展示）：

```
确认删除角色

删除角色后，角色信息及所有相关数据将被永久清除且不可恢复。
（当 friend_count > 0 时追加：）目前有 X 位用户与该角色存在好友关系，相关聊天记录也将一并清除。
即使重新创建同名角色，旧有数据也无法恢复。

确定要继续吗？

[取消]  [确认删除]
```

弹窗结构和样式复用解除好友弹窗（`Character.vue:150-175`），`Teleport` 到 body，使用 daisyUI `modal` 类。

### 改动 4 — CreateCharacter.vue：取消按钮

**文件：** `frontend/src/views/create/character/CreateCharacter.vue`

```html
<div class="card-actions justify-center mt-3 gap-4">
  <button @click="router.back()" class="btn btn-outline w-30">取消</button>
  <button @click="handleCreate" class="btn btn-neutral w-30">创建</button>
</div>
```

### 改动 5 — UpdateCharacter.vue：取消按钮

**文件：** `frontend/src/views/create/character/UpdateCharacter.vue`

```html
<div class="card-actions justify-center mt-3 gap-4">
  <button @click="router.back()" class="btn btn-outline w-30">取消</button>
  <button @click="handleUpdate" class="btn btn-neutral w-30">保存</button>
</div>
```

## 影响范围

| 文件 | 改动类型 |
|------|----------|
| `backend/web/views/create/character/get_list.py` | +import +friend_count 字段 |
| `backend/web/views/friend/get_count.py` | 新文件 |
| `backend/web/urls.py` | +import +路由 |
| `frontend/src/components/character/Character.vue` | +实时查询 +弹窗模板 +confirmRemoveCharacter |
| `frontend/src/views/create/character/CreateCharacter.vue` | +取消按钮 |
| `frontend/src/views/create/character/UpdateCharacter.vue` | +取消按钮 |

## 不改变

- 不引入软删除
- 不改变编辑流程（编辑前警告留待后续）
- 不改变现有 API 契约
- 不改变好友列表和主页的 Character 组件行为
