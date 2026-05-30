<template>
  <div class="card bg-base-100 shadow-sm border border-base-200">
    <div class="card-body p-4">
      <div class="flex items-start justify-between gap-2">
        <div class="flex-1 min-w-0">
          <h3 class="font-medium text-sm truncate">{{ doc.title }}</h3>
          <p class="text-xs text-base-content/50 mt-1">
            {{ statusText }}
          </p>
        </div>
        <span class="badge badge-sm shrink-0" :class="badgeClass">
          <span v-if="doc.status === 'processing'" class="loading loading-spinner loading-xs mr-1"></span>
          {{ statusLabel }}
        </span>
      </div>

      <div v-if="doc.status === 'failed' && doc.error_message" class="mt-2">
        <p class="text-xs text-error">{{ doc.error_message }}</p>
      </div>

      <div class="card-actions justify-end mt-3">
        <button
          class="btn btn-ghost btn-xs text-error"
          @click="emit('delete', doc.id)"
        >删除</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  doc: { type: Object, required: true },
})
const emit = defineEmits(['delete'])

const statusConfig = {
  pending:    { label: '等待中', cls: 'badge-ghost' },
  processing: { label: '处理中', cls: 'badge-info' },
  completed:  { label: '已完成', cls: 'badge-success' },
  failed:     { label: '失败', cls: 'badge-error' },
}

const statusLabel = computed(() => statusConfig[props.doc.status]?.label || props.doc.status)
const badgeClass = computed(() => statusConfig[props.doc.status]?.cls || 'badge-ghost')

const statusText = computed(() => {
  const d = props.doc
  if (d.status === 'completed') return `${d.chunks_count} 个片段 · ${d.created_at?.slice(0, 10)}`
  if (d.status === 'processing') return '解析中...'
  return d.created_at?.slice(0, 10) || ''
})
</script>
