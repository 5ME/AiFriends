<script setup lang="ts">
import api from '@/js/http/api';
import {nextTick, onBeforeUnmount, onMounted, ref, useTemplateRef, watch} from 'vue';
import Character from '@/components/character/Character.vue';
import {useRoute} from 'vue-router';

const route = useRoute()

const characters = ref([])
const isLoading = ref(false)
const hasCharacters = ref(true)
const sentinelRef = useTemplateRef('sentinel-ref')

// 判断哨兵是否在窗口内
function checkSentinelVisible() {
  if (!sentinelRef.value)
    return false
  const rect = sentinelRef.value.getBoundingClientRect()
  return rect.top < window.innerHeight && rect.bottom > 0
}

async function loadMore() {
  if (isLoading.value || !hasCharacters.value) {
    return
  }
  isLoading.value = true
  let newCharacters = []
  try {
    const response = await api.get('/api/homepage/index/', {
      params: {
        items_count: characters.value.length,
        search_text: route.query.q || ''
      }
    })
    const data = response.data
    // console.log(data)
    if (data.message === 'success') {
      newCharacters = data.characters
    }
  } catch (e) {
    console.log(e)
  } finally {
    isLoading.value = false
    if (newCharacters.length === 0) {
      hasCharacters.value = false
    } else {
      characters.value.push(...newCharacters)
      // nextTick() 是 Vue 提供的一个异步方法，用于在下次 DOM 更新循环结束之后执行延迟回调。
      // 简单说，就是等待 Vue 完成数据变更导致的 DOM 更新后，再执行某些操作。
      await nextTick()
      if (checkSentinelVisible()) {
        await loadMore()
      }
    }
  }
}

let observer = null
onMounted(async () => {
  await loadMore()
  observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            loadMore()
          }
        })
      },
      {root: null, rootMargin: '2px', threshold: 0}
  )
  observer.observe(sentinelRef.value)
})

function reset() {
  characters.value = []
  isLoading.value = false
  hasCharacters.value = true
  loadMore()
}

watch(() => route.query.q, newQ => {
  reset()
})

onBeforeUnmount(() => {
  observer?.disconnect()
})
</script>

<template>
  <div class="flex flex-col items-center">
    <div class="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-9 mt-12 justify-items-center w-full px-9">
      <Character v-for="character in characters" :key="character.id" :character="character"/>
    </div>

    <div ref="sentinel-ref" class="h-2 mt-8"></div>

    <div v-if="isLoading" class="text-gray-500 mt-4">
      <span class="loading loading-spinner loading-md"></span>
    </div>
    <div v-else-if="!hasCharacters" class="text-gray-500 mt-4">
      没有更多角色啦
    </div>
  </div>
</template>

<style scoped></style>