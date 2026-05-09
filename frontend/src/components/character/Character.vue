<script setup lang="ts">
import {ref, useTemplateRef} from "vue";
import UpdateIcon from "@/components/character/icons/UpdateIcon.vue";
import RemoveIcon from "@/components/character/icons/RemoveIcon.vue";
import {useUserStore} from "@/stores/user";
import api from "@/js/http/api";
import ChatField from "@/components/character/chat_field/ChatField.vue";
import CharacterDetail from "@/components/character/CharacterDetail.vue";
import {useRouter} from "vue-router";

const props = defineProps(['character', 'canEdit', 'canRemoveFriend', 'friendId', 'showDetail'])
const emit = defineEmits(['remove'])
const isHover = ref(false)
const router = useRouter()
const user = useUserStore()

async function handleRemoveCharacter() {
  try {
    const response = await api.post('api/create/character/remove/', {
      character_id: props.character.id
    })
    if (response.data.message === 'success') {
      emit('remove', props.character.id)
    }
  } catch (e) {
    console.log(e)
  }
}

const chatFieldRef = useTemplateRef('chat-field-ref')
const characterDetailRef = useTemplateRef('character-detail-ref')
const confirmModalRef = useTemplateRef('confirm-modal-ref')
const friend = ref(null)

function handleCardClick() {
  if (props.showDetail) {
    characterDetailRef.value.showModal()
  } else {
    openChatField()
  }
}

async function openChatField() {
  if (!user.isLogin()) {
    await router.push({name: 'user-account-login-index'})
  } else {
    try {
      const response = await api.post('/api/friend/get_or_create/', {
        character_id: props.character.id
      })
      const data = response.data
      if (data.message === 'success') {
        friend.value = data.friend
        chatFieldRef.value.showModal()
      }
    } catch (e) {
      console.log(e)
    }
  }
}

function handleRemoveFriend() {
  confirmModalRef.value.showModal()
}

async function confirmRemoveFriend() {
  try {
    const response = await api.post('/api/friend/remove/', {
      friend_id: props.friendId
    })
    if (response.data.message === 'success') {
      confirmModalRef.value.close()
      emit('remove', props.friendId)
    }
  } catch (e) {
    console.log(e)
  }
}
</script>

<template>
  <div>
    <div v-if="character" class="card card-border bg-base-100 h-100 w-60 shadow-sm cursor-pointer
                                transition-transform duration-300"
         :class="{'scale-105': isHover, 'shadow-2xl': isHover}"
         @mouseover="isHover=true" @mouseout="isHover=false"
         @click="handleCardClick">
      <figure>
        <img :src="character.background_image" alt="bg"/>
      </figure>
      <div class="card-body">
        <div class="flex gap-4">
          <div class="avatar">
            <div class="rounded-full w-10">
              <img :src="character.photo" alt=""/>
            </div>
          </div>
          <h2 class="card-title line-clamp-1 break-all">
            {{ character.name }}
          </h2>
        </div>
        <p class="line-clamp-2 break-all">
          {{ character.profile }}
        </p>
        <div class="card-actions justify-end"
             v-if="canEdit && character.author.user_id === user.id">
          <RouterLink class="btn btn-ghost btn-sm btn-circle bg-neutral-700"
                      :to="{name: 'update-character', params: {character_id: character.id}}"
                      @click.stop>
            <UpdateIcon/>
          </RouterLink>
          <button class="btn btn-ghost btn-sm btn-circle bg-red-700"
                  @click.stop="handleRemoveCharacter">
            <RemoveIcon/>
          </button>
        </div>

        <div v-if="canRemoveFriend" class="card-actions justify-end">
          <!--          <button class="btn btn-ghost btn-sm btn-circle bg-red-700"-->
          <!--                  @click="handleRemoveFriend">-->
          <!--            <RemoveIcon/>-->
          <!--          </button>-->
          <!--@click.stop 阻止事件传播，防止触发父组件的 click 事件-->
          <button @click.stop="handleRemoveFriend" class="btn btn-sm bg-red-700 text-white">
            解除好友
          </button>
        </div>
      </div>
    </div>

    <RouterLink class="flex items-center mt-2 gap-2"
                :to="{name: 'user-space-index', params: {user_id: character.author.user_id}}">
      <div class="avatar">
        <div class="rounded-full w-5">
          <img :src="character.author.photo" alt=""/>
        </div>
      </div>
      <div class="text-xs text-neutral-500 line-clamp-1 break-all">
        {{ character.author.username }}
      </div>
    </RouterLink>

    <!--角色详情框-->
    <CharacterDetail ref="character-detail-ref" :character="character"/>

    <!--聊天框-->
    <ChatField ref="chat-field-ref" :friend="friend"/>

    <!--解除好友确认框-->
    <Teleport to="body">
      <dialog ref="confirm-modal-ref" class="modal">
        <div class="modal-box">
          <form method="dialog">
            <button class="btn btn-sm btn-circle btn-ghost absolute right-3 top-3">✕</button>
          </form>
          <h3 class="text-lg font-bold mb-4">确认解除好友关系</h3>
          <p class="text leading-relaxed mb-2">
            解除好友关系后，与 <span class="font-semibold underline decoration-red-700 decoration-dashed underline-offset-4">{{ character.name }}</span> 的聊天记录也将一并清除且不可恢复。即使重新与该角色结为好友，旧有聊天记录也无法恢复。
          </p>
          <p class="text font-semibold leading-relaxed mb-6">
            确定要继续吗？
          </p>
          <div class="modal-action">
            <form method="dialog">
              <button class="btn btn-ghost">取消</button>
            </form>
            <button class="btn bg-red-700 text-white" @click="confirmRemoveFriend">确认解除</button>
          </div>
        </div>
        <form method="dialog" class="modal-backdrop">
          <button>close</button>
        </form>
      </dialog>
    </Teleport>
  </div>
</template>

<style scoped>

</style>