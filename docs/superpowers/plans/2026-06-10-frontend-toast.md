# Phase 2.1: 前端 Toast 基础设施 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立全局 toast 通知组件 — Composable + daisyUI Alert 渲染，一行代码调用。

**Architecture:** `useToast.js` 管理模块级 reactive 状态；`ToastContainer.vue` 用 daisyUI `toast` + `alert-*` 渲染；`App.vue` 挂载容器。

**Tech Stack:** Vue 3 Composition API, daisyUI 5.5, Tailwind CSS 4

**Design doc:** `docs/superpowers/specs/2026-06-10-frontend-toast-design.md`

**Note:** 前端无测试框架。Phase 2.1 不做 TDD，通过运行 dev server 手动验证。测试框架搭建属独立基建任务。

---

### File Structure

| 文件 | 职责 |
|------|------|
| `frontend/src/composables/useToast.js` | 状态 + success/error/warning/info 方法 |
| `frontend/src/components/ToastContainer.vue` | daisyUI toast + alert 渲染 |
| `frontend/src/App.vue` | 挂载 `<ToastContainer />` |

---

### Task 1: 创建 `useToast.js` Composable

**Files:**
- Create: `frontend/src/composables/useToast.js`

- [ ] **Step 1: 创建文件**

用 Write 工具写入 `frontend/src/composables/useToast.js`：

```javascript
import { reactive } from 'vue'

const state = reactive({
  toasts: []
})

let _id = 0

export function useToast() {
  function add(type, message, duration = 3000) {
    if (!message) return
    const id = ++_id
    state.toasts.push({ id, type, message })
    if (type !== 'error' && duration > 0) {
      setTimeout(() => remove(id), duration)
    }
    if (state.toasts.length > 5) {
      state.toasts.shift()
    }
  }

  function remove(id) {
    const idx = state.toasts.findIndex(t => t.id === id)
    if (idx !== -1) state.toasts.splice(idx, 1)
  }

  return {
    toasts: state.toasts,
    success: (msg) => add('success', msg),
    error:   (msg) => add('error', msg, 0),
    warning: (msg) => add('warning', msg),
    info:    (msg) => add('info', msg),
    remove,
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/composables/useToast.js
git commit -m "feat: useToast composable — 模块级 reactive 全局 toast 状态管理"
```

---

### Task 2: 创建 `ToastContainer.vue` + 修改 `App.vue`

**Files:**
- Create: `frontend/src/components/ToastContainer.vue`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: 创建 ToastContainer.vue**

用 Write 工具写入 `frontend/src/components/ToastContainer.vue`：

```vue
<template>
  <transition-group
    name="toast"
    tag="div"
    class="toast toast-top toast-center z-50"
  >
    <div
      v-for="t in toasts"
      :key="t.id"
      :class="['alert', `alert-${t.type}`]"
      class="shadow-lg"
    >
      <!-- success icon: 勾选圆圈 -->
      <svg
        v-if="t.type === 'success'"
        xmlns="http://www.w3.org/2000/svg"
        class="h-6 w-6 shrink-0 stroke-current"
        fill="none" viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round"
              stroke-width="2"
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>

      <!-- error icon: 叉号圆圈 -->
      <svg
        v-else-if="t.type === 'error'"
        xmlns="http://www.w3.org/2000/svg"
        class="h-6 w-6 shrink-0 stroke-current"
        fill="none" viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round"
              stroke-width="2"
              d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>

      <!-- warning icon: 感叹号三角 -->
      <svg
        v-else-if="t.type === 'warning'"
        xmlns="http://www.w3.org/2000/svg"
        class="h-6 w-6 shrink-0 stroke-current"
        fill="none" viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round"
              stroke-width="2"
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>

      <!-- info icon: 圆圈字母 i -->
      <svg
        v-else-if="t.type === 'info'"
        xmlns="http://www.w3.org/2000/svg"
        class="h-6 w-6 shrink-0 stroke-current"
        fill="none" viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round"
              stroke-width="2"
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>

      <span>{{ t.message }}</span>

      <!-- error 手动关闭按钮 -->
      <button
        v-if="t.type === 'error'"
        class="btn btn-ghost btn-xs ml-auto"
        @click="remove(t.id)"
      >✕</button>
    </div>
  </transition-group>
</template>

<script setup>
import { useToast } from '@/composables/useToast'
const { toasts, remove } = useToast()
</script>

<style scoped>
.toast-enter-active {
  transition: all 0.3s ease-out;
}
.toast-leave-active {
  transition: all 0.2s ease-in;
}
.toast-enter-from {
  opacity: 0;
  transform: translateY(-12px);
}
.toast-leave-to {
  opacity: 0;
}
</style>
```

- [ ] **Step 2: 修改 App.vue — 挂载 ToastContainer**

当前 `App.vue` 的 template：

```vue
<template>
  <NavBar>
    <RouterView/>
  </NavBar>
</template>
```

替换为：

```vue
<template>
  <NavBar>
    <RouterView/>
  </NavBar>
  <ToastContainer />
</template>
```

同时 script 中新增 import：

```vue
<script setup>
import ToastContainer from '@/components/ToastContainer.vue'
// ... 其他已有 import 保持不变
```

用 Edit 工具：
`old_string`:
```
<script setup>

import NavBar from "@/components/navbar/NavBar.vue";
```
`new_string`:
```
<script setup>
import ToastContainer from '@/components/ToastContainer.vue'
import NavBar from "@/components/navbar/NavBar.vue";
```

`old_string`:
```
  </NavBar>
</template>
```
`new_string`:
```
  </NavBar>
  <ToastContainer />
</template>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ToastContainer.vue frontend/src/App.vue
git commit -m "feat: ToastContainer 组件 + App.vue 挂载 — 全局 toast 通知"
```

---

### Task 3: 功能验证

- [ ] **Step 1: 启动前端 dev server**

```bash
cd frontend && npm run dev
```

- [ ] **Step 2: 浏览器控制台手动触发 toast**

在任意页面的浏览器 Console 中执行：

```javascript
// 方法 1：直接访问 composable（需要 Vue devtools）
// 实际验证方式：临时在 App.vue onMounted 中加测试代码

// 例如在 App.vue onMounted 末尾添加：
import { useToast } from '@/composables/useToast'
const toast = useToast()
toast.success('Toast 基础设施已就绪')
toast.error('这是错误通知（需手动关闭）')
toast.warning('这是警告通知')
toast.info('这是信息通知')
```

验证点：
1. 4 种类型 toast 依次出现在顶部居中
2. 颜色和图标与类型匹配
3. success/warning/info 3 秒后自动消失
4. error 不会自动消失，点击 ✕ 关闭
5. 多条 toast 堆叠不重叠
6. 超过 5 条时最早一条被移除

- [ ] **Step 3: 验证完成后移除测试代码 + 最终 Commit**

```bash
git add frontend/src/App.vue
git commit -m "chore: Phase 2.1 前端 toast 基础设施 — 功能验证通过"
```

---

*Plan Date: 2026-06-10*
*Based on: docs/superpowers/specs/2026-06-10-frontend-toast-design.md*
