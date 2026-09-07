<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/js/http/api'
import { useMediaQuery } from '@/composables/useMediaQuery.js'
import { useToast } from '@/composables/useToast.js'
import SessionList from '@/components/chat/SessionList.vue'
import ChatWindow from '@/components/chat/chat_window/ChatWindow.vue'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const isMobile = useMediaQuery('(max-width: 1023px)')

// Q1/Q2 已拍板：状态全部由路由参数派生，无内部 activeCharacterId
const activeCharacterId = computed(() => {
  const id = route.params.character_id
  return id ? Number(id) : null
})
const isHub = computed(() => activeCharacterId.value === null)

const friend = ref(null)
const friendLoading = ref(false)
const friendError = ref('')
const drawerOpen = ref(false)

// 异步竞态守卫（PR review 硬性 #1）：loadFriend 与 handleSelect 共享同一序号，
// 迟到响应（如 A 在途时切到 B，A 后返回）一律弃用，防止 URL 与窗口/高亮错位
let loadSeq = 0

async function loadFriend(characterId) {
  const seq = ++loadSeq
  friendLoading.value = true
  friendError.value = ''
  try {
    const response = await api.post('/api/friend/get_or_create/', {
      character_id: characterId,
    })
    if (seq !== loadSeq) return          // 迟到响应弃用
    friend.value = response.data.friend
  } catch (e) {
    if (seq !== loadSeq) return
    console.log(e)
    friend.value = null
    // E1 文案按 spec 定稿（404 = 角色不存在/已删除）；其余错误透传后端消息
    friendError.value = e.response?.status === 404
      ? '该角色不存在或已删除'
      : (e.response?.data?.message || '加载失败，请稍后重试')
  } finally {
    if (seq === loadSeq) friendLoading.value = false
  }
}

// N2 已拍板：会话切换 = 先 get_or_create，成功才 replace；404 留在原会话
async function handleSelect(characterId) {
  const seq = ++loadSeq
  drawerOpen.value = false
  try {
    const response = await api.post('/api/friend/get_or_create/', {
      character_id: characterId,
    })
    if (seq !== loadSeq) return          // 迟到响应弃用（含 replace 也一并取消）
    friend.value = response.data.friend   // 预取：watch 检测到一致将跳过 loadFriend
    await router.replace({ name: 'chat-index', params: { character_id: characterId } })
  } catch (e) {
    if (seq !== loadSeq) return
    console.log(e)
    toast.error(e.response?.data?.message || '切换会话失败')
  }
}

// 路由参数变化（后退/前进/直达/切换）：与预取 friend 一致则跳过，否则加载
watch(
  () => activeCharacterId.value,
  (id) => {
    if (id === null) {
      friend.value = null
      friendError.value = ''
      return
    }
    if (friend.value?.character?.id === id) return
    loadFriend(id)
  },
  { immediate: true },
)

// 移动端抽屉打开时锁定背景滚动
watch(drawerOpen, (open) => {
  document.body.style.overflow = open ? 'hidden' : ''
})

// 返回来源页：有历史栈则 back，直达深链无历史栈则兜底好友页（与 handleClose 一致）
function goBack() {
  if (window.history.state?.back) {
    router.back()
  } else {
    router.replace({ name: 'friend-index' })
  }
}

function handleClose() {
  goBack()
}
</script>

<template>
  <div class="flex h-[calc(100dvh-64px)]">
    <!-- 桌面端：会话栏常驻 -->
    <aside v-if="!isMobile" class="w-70 shrink-0 border-r border-base-300 bg-base-200">
      <SessionList :active-id="activeCharacterId" @select="handleSelect" />
    </aside>

    <!-- 移动端：会话抽屉（z-60 高于 NavBar z-50，spec §4.2「覆盖 NavBar 层」） -->
    <Teleport v-else to="body">
      <Transition name="fade">
        <div v-if="drawerOpen" class="fixed inset-0 z-[60]">
          <div class="absolute inset-0 bg-black/50" @click="drawerOpen = false"></div>
          <div class="absolute left-0 top-0 h-full w-70 bg-base-200 border-r border-base-300 shadow-xl">
            <SessionList :active-id="activeCharacterId"
                         @select="handleSelect"
                         @closeDrawer="drawerOpen = false" />
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 舞台（聊天区）：flex 居中 = 角色之窗上下左右居中（spec §4.3） -->
    <main class="flex-1 relative overflow-hidden flex items-center justify-center">
      <!-- 会话中心空态（/chat/ 无参，Q7-b 静态） -->
      <div v-if="isHub" class="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-base-200">
        <p class="text-neutral-500 text-lg">从左侧选择一个好友开始聊天</p>
        <button v-if="isMobile" type="button" class="btn btn-neutral" @click="drawerOpen = true">
          选择好友
        </button>
      </div>

      <!-- 页面加载中 -->
      <div v-else-if="friendLoading && !friend" class="absolute inset-0 flex items-center justify-center">
        <span class="loading loading-spinner loading-lg"></span>
      </div>

      <!-- 页面错误态（E1） -->
      <div v-else-if="friendError" class="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-base-200">
        <p class="text-red-500">{{ friendError }}</p>
        <button type="button" class="btn btn-neutral" @click="goBack">返回</button>
      </div>

      <!-- 会话（:key 重建 = 资源释放时序 D-L4） -->
      <ChatWindow v-else :key="friend.character.id"
                  :friend="friend"
                  @closed="handleClose"
                  @openDrawer="drawerOpen = true" />
    </main>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
