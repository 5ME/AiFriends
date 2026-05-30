import { ref, onUnmounted } from 'vue'
import { getDocumentList } from '@/js/http/api.js'

/**
 * 文档处理状态轮询。
 * 每 3 秒拉取文档列表，当全部文档到达终态时自动停止。
 * 兜底上限 120 次（6 分钟），超时提醒用户手动刷新。
 */
export function useDocumentPolling() {
  const documents = ref([])
  const isPolling = ref(false)
  let timer = null
  let pollCount = 0
  const MAX_POLLS = 120
  const isFetching = ref(false)

  async function fetchList() {
    if (isFetching.value) return  // 上一次请求未完成，跳过本次
    isFetching.value = true
    try {
      const res = await getDocumentList()
      documents.value = res.data.documents
    } catch (e) {
      console.error('文档列表拉取失败:', e)
    } finally {
      isFetching.value = false
    }
  }

  function hasProcessing() {
    return documents.value.some(
      d => d.status === 'pending' || d.status === 'processing'
    )
  }

  async function startPolling() {
    if (isPolling.value) return
    isPolling.value = true
    pollCount = 0

    await fetchList()

    if (!hasProcessing()) {
      isPolling.value = false
      return
    }

    timer = setInterval(async () => {
      pollCount++
      await fetchList()

      if (!hasProcessing() || pollCount >= MAX_POLLS) {
        clearInterval(timer)
        isPolling.value = false
        if (pollCount >= MAX_POLLS) {
          console.warn('文档处理轮询超时')
        }
      }
    }, 3000)
  }

  async function refresh() {
    await fetchList()
    // 有处理中的文档就重新启动轮询
    if (hasProcessing()) {
      startPolling()
    }
  }

  onUnmounted(() => {
    if (timer) {
      clearInterval(timer)
      isPolling.value = false
    }
  })

  return { documents, isPolling, startPolling, refresh }
}
