<script setup lang="ts">
import { computed, onMounted, ref, useTemplateRef } from 'vue'
import api from '@/js/http/api'
import SessionItem from '@/components/chat/SessionItem.vue'

const props = defineProps(['activeId', 'accent'])
const emits = defineEmits(['select', 'closeDrawer'])

const listRef = useTemplateRef('list-ref')
const sessions = ref([])
const loading = ref(false)
const error = ref('')
const hasMore = ref(true)
const keyword = ref('')

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return sessions.value
  return sessions.value.filter(s => s.character.name.toLowerCase().includes(kw))
})

async function loadMore() {
  if (loading.value || !hasMore.value) return
  loading.value = true
  error.value = ''
  try {
    const response = await api.get('/api/friend/get_list/', {
      params: { items_count: sessions.value.length },
    })
    const friends = response.data.friends || []
    sessions.value.push(...friends)
    hasMore.value = friends.length === 20
  } catch (e) {
    console.log(e)
    error.value = e.response?.data?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function handleScroll() {
  const el = listRef.value
  if (!el) return
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 24) {
    loadMore()
  }
}

function handleSelect(characterId) {
  emits('select', characterId)
  emits('closeDrawer')
}

onMounted(() => {
  loadMore()
})
</script>

<template>
  <div class="flex flex-col h-full" :style="{ '--accent': props.accent }">
    <!-- 搜索区（56px） -->
    <div class="h-14 shrink-0 px-3 flex items-center">
      <input v-model="keyword"
             type="text"
             placeholder="搜索好友"
             aria-label="搜索好友"
             class="input input-sm rounded-full w-full bg-base-100" />
    </div>

    <!-- 列表区 -->
    <div ref="list-ref" class="flex-1 min-h-0 overflow-y-auto no-scrollbar px-2 pb-2"
         @scroll="handleScroll">
      <!-- loading 骨架 -->
      <template v-if="loading && sessions.length === 0">
        <div v-for="i in 3" :key="i" class="flex items-center gap-3 px-2 h-16">
          <div class="w-10 h-10 rounded-full skeleton-shimmer"></div>
          <div class="h-4 w-24 rounded skeleton-shimmer"></div>
        </div>
      </template>

      <!-- 列表 -->
      <template v-else-if="sessions.length > 0">
        <SessionItem v-for="s in filtered"
                     :key="s.id"
                     :session="s"
                     :active="Number(props.activeId) === s.character.id"
                     @select="handleSelect" />
        <p v-if="filtered.length === 0" class="text-center text-sm text-neutral-500 py-6">
          没有匹配的好友
        </p>
      </template>

      <!-- 空态 -->
      <div v-else-if="!loading && !error" class="text-center py-10">
        <p class="text-sm text-neutral-500 mb-3">还没有好友，去首页添加吧</p>
        <RouterLink :to="{ name: 'homepage-index' }" class="btn btn-sm btn-neutral">去首页</RouterLink>
      </div>

      <!-- 错误态 -->
      <div v-if="error" class="text-center py-8">
        <p class="text-sm text-red-500 mb-3">{{ error }}</p>
        <button type="button" class="btn btn-sm btn-neutral" @click="loadMore">重试</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
</style>
