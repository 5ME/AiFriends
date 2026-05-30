<template>
  <div
    class="upload-zone border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer"
    :class="[
      isDragOver ? 'border-primary bg-primary/5' : 'border-base-300',
      isUploading ? 'pointer-events-none opacity-50' : 'hover:border-primary/50'
    ]"
    @dragover.prevent="isDragOver = true"
    @dragleave.prevent="isDragOver = false"
    @drop.prevent="handleDrop"
    @click="triggerFileInput"
  >
    <input
      ref="fileInput"
      type="file"
      accept=".txt,.md,.pdf"
      class="hidden"
      @change="handleFileSelect"
    />

    <div v-if="isUploading" class="flex flex-col items-center gap-2">
      <span class="loading loading-spinner loading-md"></span>
      <span class="text-sm text-base-content/60">上传中...</span>
    </div>
    <div v-else class="flex flex-col items-center gap-2">
      <svg class="w-10 h-10 text-base-content/30" fill="none" stroke="currentColor"
           viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round"
           stroke-width="1.5" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25
           2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"/></svg>
      <span class="text-sm font-medium">拖拽文件到此处</span>
      <span class="text-xs text-base-content/40">或点击上传</span>
      <span class="text-xs text-base-content/30 mt-2">
        支持 .txt .md .pdf · 单文件 ≤ 10MB
      </span>
      <p v-if="errorMessage" class="text-xs text-error mt-2">{{ errorMessage }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const emit = defineEmits(['upload'])
const fileInput = ref(null)
const isDragOver = ref(false)
const isUploading = ref(false)
const errorMessage = ref('')

function validate(file) {
  const allowed = ['txt', 'md', 'pdf']
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!allowed.includes(ext)) return '不支持的文件格式，仅支持 txt/md/pdf'
  if (file.size > 10 * 1024 * 1024) return '文件大小不能超过 10MB'
  return null
}

function handleFile(file) {
  const error = validate(file)
  if (error) {
    errorMessage.value = error
    return
  }
  errorMessage.value = ''
  isUploading.value = true
  emit('upload', file, () => { isUploading.value = false })
}

function handleDrop(e) {
  isDragOver.value = false
  const file = e.dataTransfer.files[0]
  if (file) handleFile(file)
}

function handleFileSelect(e) {
  const file = e.target.files[0]
  if (file) handleFile(file)
  e.target.value = ''  // 允许重复选同一文件
}

function triggerFileInput() {
  if (!isUploading.value) fileInput.value?.click()
}
</script>
