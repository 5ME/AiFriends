import { ref, onMounted, onBeforeUnmount } from 'vue'

/**
 * 响应式媒体查询（项目无 @vueuse，自建 matchMedia 封装，约 10 行）。
 * 用法：const isMobile = useMediaQuery('(max-width: 1023px)')
 */
export function useMediaQuery(query) {
  const matches = ref(false)
  let mql = null

  const update = () => {
    matches.value = mql ? mql.matches : false
  }

  onMounted(() => {
    mql = window.matchMedia(query)
    update()
    mql.addEventListener('change', update)
  })

  onBeforeUnmount(() => {
    if (mql) {
      mql.removeEventListener('change', update)
      mql = null
    }
  })

  return matches
}
