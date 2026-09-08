<script setup lang="ts">
import { computed, nextTick, ref, useTemplateRef, watch } from 'vue'
import {useUserStore} from '@/stores/user';
import { useToast } from '@/composables/useToast'
import { formatTime } from '@/utils/chatFormat'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps({
  message: { type: Object, required: true },
  character: Object,
  showHeader: { type: Boolean, default: true },
  dateLabel: { type: String, default: null },
})
const emits = defineEmits(['openCitation'])

const user = useUserStore()
const toast = useToast()

const avatar = computed(() =>
  props.message.role === 'ai' ? props.character?.photo : user.photo
)
const name = computed(() =>
  props.message.role === 'ai' ? props.character?.name : user.username
)

// markdown：始终渲染（2026-09-08 修订：原 D-L5「流式结束才渲染」导致裸文本+代码块标记长时间裸露，
// 改为边收边渲染；marked+DOMPurify 对增量文本开销可忽略）
const renderedHtml = computed(() =>
  props.message.content ? renderMarkdown(props.message.content) : ''
)

// 代码块右上角「复制」按钮（v-html 内容不携带 scope 属性，样式经 :deep 前缀挂载）
const bubbleContentRef = useTemplateRef('bubble-content-ref')

function attachCopyButtons() {
  const root = bubbleContentRef.value
  if (!root) return
  root.querySelectorAll('pre').forEach((pre) => {
    if (pre.dataset.copyBound) return  // 幂等：仅挂一次
    pre.dataset.copyBound = '1'
    const codeText = pre.querySelector('code')?.textContent ?? pre.textContent ?? ''
    const btn = document.createElement('button')
    btn.type = 'button'
    btn.className = 'code-copy-btn'
    btn.setAttribute('aria-label', '复制代码')
    btn.textContent = '复制'
    btn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(codeText)
        toast.success('代码已复制')
      } catch (e) {
        toast.error('复制失败，请手动选择复制')
      }
    })
    pre.appendChild(btn)
  })
}

watch(
  () => props.message.content,
  () => { nextTick(attachCopyButtons) },
  { immediate: true },
  { immediate: true }  // 历史消息挂载即 rendered
)

</script>

<template>
  <div v-if="message.content" :class="showHeader ? 'mt-3' : 'mt-1'">
    <!-- 日期分隔胶囊（组首 + 与上一条跨天时） -->
    <div v-if="dateLabel" class="flex justify-center my-2">
      <span class="date-capsule">{{ dateLabel }}</span>
    </div>

    <!-- 组首：头像 + 名字 pill（N1 底衬保证亮图可读） -->
    <div v-if="showHeader" class="flex items-center gap-2 mb-1"
         :class="message.role === 'user' ? 'flex-row-reverse' : ''">
      <div class="avatar shrink-0">
        <div class="w-9 rounded-full">
          <img :src="avatar" alt=""/>
        </div>
      </div>
      <span class="msg-name-pill">{{ name }}</span>
    </div>

    <!-- 气泡（spec §8.2：break-words、max-w 75%、圆角 16px 头像侧 4px）+ hover 时间 -->
    <div class="group flex items-end gap-1.5"
         :class="message.role === 'user' ? 'justify-end' : 'justify-start'">
      <span v-if="message.time && message.role === 'user'"
            class="opacity-0 group-hover:opacity-100 transition-opacity text-white/60 text-[11px] shrink-0 pb-0.5">
        {{ formatTime(message.time) }}
      </span>

      <div class="msg-bubble"
           :class="message.role === 'user' ? 'msg-bubble-user' : 'msg-bubble-ai'">
        <div ref="bubble-content-ref"
             class="msg-markdown"
             v-html="renderedHtml"></div>
      </div>

      <span v-if="message.time && message.role === 'ai'"
            class="opacity-0 group-hover:opacity-100 transition-opacity text-white/60 text-[11px] shrink-0 pb-0.5">
        {{ formatTime(message.time) }}
      </span>
    </div>

    <!-- RAG 引用 chips（Phase 2：替换 collapse；点击弹浮层显示原文） -->
    <div v-if="message.role === 'ai' && message.citations?.length"
         class="flex flex-wrap gap-1.5 mt-1.5">
      <button v-for="c in message.citations" :key="c.index"
              type="button"
              class="bg-black/25 backdrop-blur text-white/90 rounded-full px-2.5 py-1 text-xs
                     cursor-pointer hover:bg-black/40 transition-colors max-w-48"
              :aria-label="`查看参考来源：《${c.title || '系统知识库'}》 第${c.chunk_index + 1}段`"
              @click="emits('openCitation', c)">
        <span class="truncate">📖 {{ c.title || '系统知识库' }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
/* markdown 渲染内容（v-html 无 scope 属性 → 经 .msg-markdown 根用 :deep 下钻） */
.msg-markdown {
  white-space: normal;
}
.msg-markdown :deep(p) { margin: 0.4em 0; }
.msg-markdown :deep(p:first-child) { margin-top: 0; }
.msg-markdown :deep(p:last-child) { margin-bottom: 0; }
.msg-markdown :deep(ul), .msg-markdown :deep(ol) { margin: 0.4em 0; padding-left: 1.3em; }
.msg-markdown :deep(ul) { list-style: disc; }
.msg-markdown :deep(ol) { list-style: decimal; }
.msg-markdown :deep(li) { margin: 0.2em 0; }
.msg-markdown :deep(h1), .msg-markdown :deep(h2),
.msg-markdown :deep(h3), .msg-markdown :deep(h4) { font-weight: 600; line-height: 1.3; margin: 0.5em 0 0.3em; }
.msg-markdown :deep(h1) { font-size: 1.25em; }
.msg-markdown :deep(h2) { font-size: 1.18em; }
.msg-markdown :deep(h3) { font-size: 1.1em; }
.msg-markdown :deep(h4) { font-size: 1.05em; }
.msg-markdown :deep(code) { background: rgba(0, 0, 0, 0.4); border-radius: 4px; padding: 0.1em 0.35em; font-size: 0.85em; }
.msg-markdown :deep(pre) { position: relative; background: rgba(0, 0, 0, 0.45); border-radius: 8px; padding: 0.6em 0.8em; margin: 0.5em 0; overflow-x: auto; }
.msg-markdown :deep(pre code) { background: transparent; padding: 0; }
.msg-markdown :deep(blockquote) { border-left: 3px solid rgba(255, 255, 255, 0.3); padding-left: 0.7em; margin: 0.4em 0; color: rgba(255, 255, 255, 0.85); }
.msg-markdown :deep(a) { color: #7dd3fc; text-decoration: underline; word-break: break-all; }

/* 代码块复制按钮（动态注入 DOM，样式经 .msg-markdown 下钻以享受 scoped 隔离） */
.msg-markdown :deep(pre .code-copy-btn) {
  position: absolute;
  top: 4px;
  right: 4px;
  background: rgba(0, 0, 0, 0.5);
  color: rgba(255, 255, 255, 0.85);
  font-size: 11px;
  line-height: 1;
  padding: 3px 8px;
  border-radius: 9999px;
  cursor: pointer;
  border: none;
}
.msg-markdown :deep(pre .code-copy-btn:hover) { background: rgba(0, 0, 0, 0.75); }
</style>
