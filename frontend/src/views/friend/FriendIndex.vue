<script setup lang="ts">
import api from "@/js/http/api";
import {nextTick, onBeforeMount, onBeforeUnmount, onMounted, ref, useTemplateRef} from "vue";
import Character from "@/components/character/Character.vue";

const sentinelRef = useTemplateRef('sentinel-ref')
const friends = ref([])
const isLoading = ref(false)
const hasFriends = ref(true)

// 判断哨兵是否在窗口内
function checkSentinelVisible() {
  if (!sentinelRef.value)
    return false
  const rect = sentinelRef.value.getBoundingClientRect()
  return rect.top < window.innerHeight && rect.bottom > 0
}

async function loadMore() {
  if (isLoading.value || !hasFriends.value) {
    return
  }
  isLoading.value = true
  let newFriends = []
  try {
    const response = await api.get('api/friend/get_list/', {
      params: {
        items_count: friends.value.length
      }
    })
    const data = response.data
    if (data.message === 'success') {
      newFriends = data.friends
    }
  } catch (e) {
    console.log(e)
  } finally {
    isLoading.value = false
    if (newFriends.length === 0) {
      hasFriends.value = false
    } else {
      friends.value.push(...newFriends)
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
      entries => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            // console.log("哨兵出现")
            loadMore()
          }
        })
      },
      {root: null, rootMargin: '2px', threshold: 0}
  )
  observer.observe(sentinelRef.value)
})

function removeFriend(friendId) {
  friends.value = friends.value.filter(f => f.id != friendId)
}

onBeforeUnmount(() => {
  observer?.disconnect()
})
</script>

<template>
  <div class="flex flex-col items-center mb-12">
    <div class="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-9 mt-12 justify-items-center w-full px-9">
      <Character v-for="friend in friends"
                 :key="friend.id"
                 :character="friend.character"
                 :canRemoveFriend="true"
                 :friendId="friend.id"
                 @remove="removeFriend"/>
    </div>

    <!--定义一个哨兵，用于判断是否需要加载数据-->
    <div ref="sentinel-ref" class="h-2 mt-8"></div>

    <div v-if="isLoading" class="text-gray-500 mt-4">
      <span class="loading loading-spinner loading-md"></span>
    </div>
    <div v-else-if="!hasFriends" class="text-gray-500 mt-4">
      没有更多聊天啦
    </div>
  </div>
</template>

<style scoped>

</style>