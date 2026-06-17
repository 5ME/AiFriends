# P1-B1: 前端展示 RAG citations — 设计文档

> 日期：2026-06-17  
> 来源：`docs/superpowers/specs/2026-06-11-next-steps-roadmap.md` P1-B1  
> 状态：待实施

---

## 一、问题陈述

后端 SSE 已发送 `{"citations": [...]}` 事件（包含文档标题 + 段落号），但前端 `InputField.vue` 静默忽略。用户看不到 AI 回答的引用来源。

---

## 二、数据流

```
后端 SSE                         前端
────────                         ────
{"citations": [            →     InputField.vue onmessage
  {index, title,                 ↓
   chunk_index}, ...            emits('appendToLastMessage',
]}                                 {citations: [...]})
                                  ↓
{"content": "根据资料..."  →     emits('appendToLastMessage',
                                  '根据资料...')
                                  ↓
                              Message.vue
                              渲染 content + citations 面板
```

### citation 数据格式

```json
{
  "index": 1,
  "title": "西游记角色介绍",
  "chunk_index": 2
}
```

---

## 三、组件改动

### 3.1 `Message.vue` — 新增 citations 面板

在 AI 消息气泡下方，`message.citations` 存在时渲染折叠面板：

```
┌─────────────────────────────────────┐
│ 红孩儿                              │
│ ┌─────────────────────────────────┐ │
│ │ 根据资料，红孩儿是...           │ │
│ └─────────────────────────────────┘ │
│ 📚 参考来源 (2)                ▾    │
│ ┌─────────────────────────────────┐ │
│ │ 1. 西游记角色介绍 · 第2段      │ │
│ │ 2. 红孩儿背景资料 · 第5段      │ │
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
```

- 使用 daisyUI `collapse`（折叠面板），默认收起
- 标题格式：`{index}. {title} · 第{chunk_index}段`
- 只有 AI 消息且 `message.citations` 非空时才显示
- 如果知识库返回无标题（系统知识库），显示 "系统知识库"

### 3.2 `InputField.vue` — 捕获 citations 事件

`onmessage` 回调新增一个分支：

```javascript
if (data.citations) {
  emits('appendToLastMessage', {citations: data.citations})
}
```

**时序保证：** 后端确保 citations 事件先于 content 发送（`chat.py:374` 注释），所以 citations 总是先挂到消息上再追加文本。

---

## 四、不涉及

- 不展示 citation 对应的文档内容片段（chunk content 后端未发送）
- 不修改后端 SSE 协议
- 不引入新依赖

---

## 五、测试

- 手动：在知识库中有文档的好友对话框发送触发 RAG 的问题 → 验证 citations 面板出现
- 手动：发送不触发 RAG 的问题 → 验证无 citations 面板
- CI 不做前端测试（当前 CI 不包含前端测试）
