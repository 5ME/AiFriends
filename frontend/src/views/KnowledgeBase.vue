<template>
  <div class="max-w-4xl mx-auto p-6">
    <h1 class="text-2xl font-bold mb-1">知识库</h1>
    <p class="text-sm text-base-content/50 mb-6">
      上传你的文档，AI 将在聊天时引用其中的内容
    </p>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <!-- 左侧上传区 -->
      <div>
        <UploadZone @upload="handleUpload" />
      </div>

      <!-- 右侧文档列表 -->
      <div>
        <div v-if="documents.length === 0" class="flex flex-col items-center justify-center h-full text-base-content/30 py-16">
          <svg class="w-16 h-16 mb-4" fill="none" stroke="currentColor"
               viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round"
               stroke-width="1" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1
               1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
          <p class="text-sm">暂无文档</p>
          <p class="text-xs mt-1">上传你的第一个文档吧</p>
        </div>

        <div v-else class="space-y-3">
          <DocumentCard
            v-for="doc in documents"
            :key="doc.id"
            :doc="doc"
            @delete="confirmDelete"
          />
        </div>
      </div>
    </div>

    <!-- 上传/删除错误提示 -->
    <p v-if="uploadError" class="text-error text-sm mt-2">{{ uploadError }}</p>

    <!-- daisyUI 删除确认 Modal -->
    <dialog class="modal" :class="{ 'modal-open': showDeleteModal }">
      <div class="modal-box">
        <h3 class="text-lg font-bold">确认删除</h3>
        <p class="py-4">删除后文档及其所有片段将被永久移除，不可恢复。</p>
        <div class="modal-action">
          <button class="btn" @click="showDeleteModal = false">取消</button>
          <button class="btn bg-red-700 text-white" @click="handleDelete">确认删除</button>
        </div>
      </div>
    </dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import UploadZone from '@/components/knowledge/UploadZone.vue'
import DocumentCard from '@/components/knowledge/DocumentCard.vue'
import { uploadDocument, removeDocument } from '@/js/http/api.js'
import { useDocumentPolling } from '@/composables/useDocumentPolling.js'

const { documents, startPolling, refresh } = useDocumentPolling()
const uploadError = ref('')
const deleteTargetId = ref(null)
const showDeleteModal = ref(false)

onMounted(() => {
  startPolling()
})

async function handleUpload(file, done) {
  uploadError.value = ''
  try {
    await uploadDocument(file)
    await refresh()
  } catch (e) {
    uploadError.value = e.response?.data?.message || '上传失败，请重试'
  } finally {
    done()
  }
}

function confirmDelete(docId) {
  deleteTargetId.value = docId
  showDeleteModal.value = true
}
async function handleDelete() {
  const docId = deleteTargetId.value
  showDeleteModal.value = false

  const idx = documents.value.findIndex(d => d.id === docId)
  const removed = documents.value.splice(idx, 1)[0]

  try {
    await removeDocument(docId)
  } catch (e) {
    documents.value.splice(idx, 0, removed)
    uploadError.value = e.response?.data?.message || '删除失败'
  }
}
</script>
