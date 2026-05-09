<script setup lang="ts">
import {ref, useTemplateRef} from "vue";
import {useUserStore} from "@/stores/user";
import {useRouter} from "vue-router";
import api from "@/js/http/api";
import ChatField from "@/components/character/chat_field/ChatField.vue";

const props = defineProps({
  character: Object,
  mode: {type: String, default: 'card'},  // 'card' = homepage flow, 'chat' = info-only
})

const router = useRouter()
const user = useUserStore()

const modalRef = useTemplateRef('modal-ref')
const chatFieldRef = useTemplateRef('chat-field-ref')
const isFriend = ref(false)
const friendId = ref(null)
const friend = ref(null)
const isLoading = ref(true)

async function showModal() {
  if (props.mode === 'card' && !user.isLogin()) {
    await router.push({name: 'user-account-login-index'})
    return
  }
  modalRef.value.showModal()
  if (props.mode === 'chat') return

  isLoading.value = true
  try {
    const response = await api.get('/api/friend/is_friend/', {
      params: {character_id: props.character.id}
    })
    if (response.data.message === 'success') {
      isFriend.value = response.data.is_friend
      friendId.value = response.data.friend_id
    }
  } catch (e) {
    console.log(e)
  } finally {
    isLoading.value = false
  }
}

async function handleAction() {
  try {
    const response = await api.post('/api/friend/get_or_create/', {
      character_id: props.character.id
    })
    if (response.data.message === 'success') {
      friend.value = response.data.friend
      modalRef.value.close()
      chatFieldRef.value.showModal()
    }
  } catch (e) {
    console.log(e)
  }
}

defineExpose({showModal})
</script>

<template>
  <Teleport to="body">
    <dialog ref="modal-ref" class="modal">
    <div class="modal-box w-120 max-h-[90vh] overflow-y-auto">
      <button class="btn btn-sm btn-circle btn-ghost absolute right-3 top-3 z-10"
              @click="modalRef.close()">
        ✕
      </button>

      <!-- 背景图 -->
      <div class="h-40 -mx-6 -mt-6 mb-4 overflow-hidden rounded-t-2xl">
        <img :src="character.background_image" alt=""
             class="w-full h-full object-cover" />
      </div>

      <!-- 角色头像 + 名称 -->
      <div class="flex items-center gap-4 -mt-12 relative z-10 mb-4">
        <div class="avatar">
          <div class="w-20 rounded-full ring-4 ring-base-100">
            <img :src="character.photo" alt="" />
          </div>
        </div>
        <h2 class="text-2xl font-bold mt-8">{{ character.name }}</h2>
      </div>

      <!-- 角色简介 -->
      <div class="mb-6">
        <p class="text-base whitespace-pre-wrap leading-relaxed">{{ character.profile.split('\n')[0] }}</p>
      </div>

      <!-- 作者信息 -->
      <RouterLink class="flex items-center gap-2 mb-6"
                  :to="{name: 'user-space-index', params: {user_id: character.author.user_id}}">
        <div class="avatar">
          <div class="w-8 rounded-full">
            <img :src="character.author.photo" alt="" />
          </div>
        </div>
        <span class="text-sm text-neutral-500">{{ character.author.username }}</span>
      </RouterLink>

      <!-- 操作按钮（仅 card 模式） -->
      <div v-if="mode === 'card'" class="card-actions justify-end">
        <button v-if="isLoading" class="btn btn-neutral" disabled>
          <span class="loading loading-spinner"></span>
        </button>
        <button v-else-if="isFriend" class="btn btn-neutral" @click="handleAction">
          开始聊天
        </button>
        <button v-else class="btn btn-neutral" @click="handleAction">
          添加好友
        </button>
      </div>
    </div>

    <!-- 聊天框（仅 card 模式） -->
    <ChatField v-if="mode === 'card'" ref="chat-field-ref" :friend="friend" />
  </dialog>
  </Teleport>
</template>

<style scoped>

</style>
