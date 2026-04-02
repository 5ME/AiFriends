<script setup lang="ts">
import {useRoute, useRouter} from "vue-router";
import UserInfoField from "@/views/user/space/components/UserInfoField.vue";
import {nextTick, onBeforeUnmount, onMounted, ref, useTemplateRef, watch} from "vue";
import api from "@/js/http/api";
import Character from "@/components/character/Character.vue";

const route = useRoute()
// 注意与下面这行区分，两者用处不一样
// const router = useRouter()

const sentinelRef = useTemplateRef('sentinel-ref')
const userProfile = ref(null)
const characters = ref([])
const isLoading = ref(false)
const hasCharacters = ref(true)

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
    const response = await api.get('/api/create/character/get_list/', {
      params: {
        items_count: characters.value.length,
        user_id: route.params.user_id
      }
    })
    const data = response.data
    // console.log(data)
    if (data.message === 'success') {
      userProfile.value = data.user_profile
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

watch(() => route.params.user_id, async () => {
  userProfile.value = null
  characters.value = []
  isLoading.value = false
  hasCharacters.value = true
  await loadMore()
})

function removeCharacter(characterId) {
  characters.value = characters.value.filter(c => c.id !== characterId)
}

onBeforeUnmount(() => {
  observer?.disconnect()
})
</script>

<template>
  <!--  空间：{{ route.params.user_id }}  -->
  <div class="flex flex-col items-center mb-12">
    <UserInfoField :userProfile="userProfile"/>
    <div class="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-9 mt-12 justify-items-center w-full px-9">
      <Character v-for="character in characters"
                 :key="character.id"
                 :character="character"
                 :canEdit="true"
                 @remove="removeCharacter"
      />
    </div>

    <!--定义一个哨兵，用于判断是否需要加载数据-->
    <div ref="sentinel-ref" class="h-2 mt-8"></div>

    <div v-if="isLoading" class="text-gray-500 mt-4">
      <span class="loading loading-spinner loading-md"></span>
    </div>
    <div v-else-if="!hasCharacters" class="text-gray-500 mt-4">
      没有更多角色啦
    </div>
  </div>
</template>

<style scoped>

</style>