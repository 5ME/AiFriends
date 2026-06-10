# Phase 2.1: 前端 Toast 基础设施 — 设计文档

> **Date:** 2026-06-10 | **Phase:** 2.1 | **Priority:** P2
> **基于:** roadmap §Phase 2, 项目Review报告(2026-05-31)

## 1. 问题

前端 8 个组件各自用 `errorMessage.value` + 内联 `<p v-if>` 展示错误信息，存在问题：

- **不统一**：每个组件自己写错误展示 UI，模式相似但细节各异
- **不显眼**：错误淹没在表单中，用户可能注意不到
- **不消失**：errorMessage 不清空就永久显示
- **不可复用**：新组件重复造轮子

## 2. 设计目标

- 全局统一 toast 通知组件，一行代码调用
- 4 种类型：success / error / warning / info
- success/info/warning 3 秒自动消失，error 手动关闭
- 顶部居中堆叠，最多 5 条
- 使用 daisyUI 5 原生 Alert + Toast 样式，不重复造轮子

## 3. 设计决策

### 3.1 架构：Composable

**选：`useToast` Composable（模块级 reactive 状态）。  
不选：Pinia Store 或 provide/inject。**

| | Composable（选） | Pinia Store（不选） | provide/inject（不选） |
|---|---|---|---|
| 调用方式 | `toast.error('...')` | `useToastStore().error('...')` | `inject('toast').error('...')` |
| 依赖 | 无 | Pinia | 需在 Vue 组件内 |
| DevTools | 无需 | 可调试 | 不可 |
| JS 函数中使用 | ✅ | ✅ | ❌ |

选择理由：

1. **toast 是通知，不是数据。** 不需持久化、不需 modules、不需 DevTools。Pinia 是数据管理工具，管 UI 通知是 overkill。
2. **团队已有 Composable 模式。** `useDocumentPolling.js`、`useImageCropper.js` 就是 composable。加一个 `useToast.js` 沿用现有模式。
3. **可在 JS 中调用。** provide/inject 只能在 Vue 组件 setup 内使用。未来 HTTP interceptor 想弹 toast 做不到。

不选 Pinia 的理由：toast 状态无需持久化（页面刷新后 toast 本就不该保留），启用 Pinia 仅为了 toast 是大材小用。

不选 provide/inject 的理由：无法在非 Vue 组件（HTTP interceptor、工具函数）中调用 toast，限制了使用场景。

### 3.2 位置：顶部居中

**选：`toast toast-top toast-center`。  
不选：右上角或右下角。**

选择理由：操作反馈类通知顶部居中最显眼，用户完成上传/提交等操作后视线自然在上方。移动端也友好。

### 3.3 error 行为：手动关闭

**选：error 需点击 ✕ 关闭。  
不选：error 也自动消失。**

选择理由：错误信息是用户需要阅读并采取行动的重要信息（"上传失败"、"网络异常"）。3 秒自动消失可能导致用户错过关键错误。

### 3.4 图标：daisyUI 内置 SVG

daisyUI 的 `alert-*` 样式自带内联 SVG 图标（勾选圆 / 叉号圆 / 警告三角 / 信息圆），不使用 emoji。图标颜色跟随 alert type 自动匹配。

## 4. 实现方案

### 4.1 文件结构

| 文件 | 职责 | 状态 |
|------|------|------|
| `frontend/src/composables/useToast.js` | 状态管理 + 方法（success/error/warning/info/remove） | 新增 |
| `frontend/src/components/ToastContainer.vue` | 渲染层（daisyUI toast + alert） | 新增 |
| `frontend/src/App.vue` | 引用 `<ToastContainer />` | 修改 |

### 4.2 useToast.js

```javascript
import { reactive } from 'vue'

const state = reactive({
  toasts: []
})

let _id = 0

export function useToast() {
  function add(type, message, duration = 3000) {
    if (!message) return    // 空字符串不显示
    const id = ++_id
    state.toasts.push({ id, type, message })
    if (type !== 'error') {
      setTimeout(() => remove(id), duration)
    }
    // 最多 5 条
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
    error:   (msg) => add('error', msg, 0),      // 0 = 不自动消失
    warning: (msg) => add('warning', msg),
    info:    (msg) => add('info', msg),
    remove,
  }
}
```

### 4.3 ToastContainer.vue

```vue
<template>
  <div class="toast toast-top toast-center z-50">
    <div
      v-for="toast in toasts"
      :key="toast.id"
      :class="['alert', `alert-${toast.type}`]"
    >
      <svg v-if="toast.type === 'success'" ... ></svg>
      <svg v-else-if="toast.type === 'error'" ... ></svg>
      <svg v-else-if="toast.type === 'warning'" ... ></svg>
      <svg v-else-if="toast.type === 'info'" ... ></svg>
      <span>{{ toast.message }}</span>
      <button
        v-if="toast.type === 'error'"
        class="btn btn-ghost btn-xs"
        @click="remove(toast.id)"
      >✕</button>
    </div>
  </div>
</template>
```

四种 SVG 内联图标对应 daisyUI 标准（`alert-success` 勾选圆、`alert-error` 叉号圆、`alert-warning` 感叹号三角、`alert-info` 字母 i 圆）。

### 4.4 App.vue 修改

```vue
<template>
  <NavBar>
    <RouterView/>
  </NavBar>
  <ToastContainer />   <!-- 新增 -->
</template>

<script setup>
import ToastContainer from '@/components/ToastContainer.vue'
```

### 4.5 调用方式

```javascript
import { useToast } from '@/composables/useToast'
const toast = useToast()

toast.success('文档已上传')
toast.error('上传失败，请重试')
toast.warning('文件大小接近上限')
toast.info('支持 txt/md/pdf 格式')
```

## 5. 边界情况

| 场景 | 行为 |
|------|------|
| 超过 5 条 | 自动移除最早的 toast |
| 同一组件多次调用 | 模块级 reactive 共享状态，所有实例看到同一列表 |
| 页面切换 | toast 不清空（路由级），跨页面可见 |
| error 未手动关闭 + 页面切换 | 保留在列表中（用户回来仍可见） |
| 极短消息（空字符串） | 不显示（`add()` 中校验） |

## 6. 测试

| # | 测试 | 验证点 |
|---|------|--------|
| 1 | success 自动消失 | 3 秒后 toast 从 DOM 移除 |
| 2 | error 手动关闭 | 点击 ✕ 后 toast 移除 |
| 3 | 多条堆叠 | 3 条 toast 按顺序排列 |
| 4 | 超 5 条 truncate | 第 6 条挤掉最早一条 |
| 5 | remove 指定 ID | 删除特定 toast |

使用 Vitest + @vue/test-utils（前端测试框架）。

## 7. 后续（Phase 3.5）

Phase 2.1 只建立 toast 基础设施（工具本身）。各组件中 `errorMessage` → `toast.error()` 的替换在 Phase 3.5 统一进行，避免本次变更范围过大。

## 8. 影响范围

| 文件 | 变更 |
|------|------|
| `frontend/src/composables/useToast.js` | 新增 |
| `frontend/src/components/ToastContainer.vue` | 新增 |
| `frontend/src/App.vue` | 修改（+1 行 import + 1 行模板） |

---

*Design Date: 2026-06-10*
*Based on: roadmap Phase 2, 前端 8 组件 errorMessage 现状*
