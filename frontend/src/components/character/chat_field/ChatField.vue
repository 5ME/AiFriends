<script setup lang="ts">
import {computed, nextTick, ref, useTemplateRef} from "vue";
import InputField from "@/components/character/chat_field/input_field/InputField.vue";
import CharacterPhotoField from "@/components/character/chat_field/character_photo_field/CharacterPhotoField.vue";
import VoiceToggle from "@/components/character/chat_field/VoiceToggle.vue";
import ChatHistory from "@/components/character/chat_field/chat_history/ChatHistory.vue";

const props = defineProps(['friend'])

const modalRef = useTemplateRef('modal-ref')
const inputRef = useTemplateRef('input-ref')
const chatHistoryRef = useTemplateRef('chat-history-ref')

const history = ref([])

async function showModal() {
  modalRef.value.showModal()
  await nextTick()
  inputRef.value.focus()
}

const modalStyle = computed(() => {
  if (props.friend) {
    return {
      backgroundImage: `url(${props.friend.character.background_image})`,
      backgroundSize: 'cover',
      backgroundPosition: 'center',
      backgroundRepeat: 'no-repeat',
    }
  } else {
    return {}
  }
})

function handlePushBackMessage(msg) {
  history.value.push(msg)
  chatHistoryRef.value.scrollToBottom()
}

function handleAppendToLastMessage(delta) {
  const last = history.value[history.value.length - 1]
  // citations 对象挂到消息上，文本追加到 content
  if (typeof delta === 'object') {
    if (delta.citations) {
      last.citations = delta.citations
    }
  } else {
    last.content += delta
  }
  chatHistoryRef.value.scrollToBottom()
}

function handlePushFrontMessage(msg) {
  history.value.unshift(msg)
}

function handleClose() {
  modalRef.value.close()
  inputRef.value.closeMic()
}

defineExpose({showModal})
</script>

<template>
  <dialog ref="modal-ref" class="modal" @close="handleClose">
    <div class="modal-box w-90 h-150" :style="modalStyle">
      <form method="dialog">
        <button class="btn btn-sm btn-circle btn-ghost absolute right-3 top-3">
          ✕
        </button>
      </form>

      <!--顶部左侧：角色头像 + 语音开关-->
      <div class="absolute left-3 top-3 flex items-center gap-2">
        <CharacterPhotoField v-if="friend"
                             :character="friend.character"
        />
        <VoiceToggle />
      </div>

      <!--聊天记录-->
      <ChatHistory v-if="friend"
                   :friendId="friend.id"
                   :character="friend.character"
                   :history="history"
                   ref="chat-history-ref"
                   @pushFrontMessage="handlePushFrontMessage"
      />

      <!--输入框-->
      <InputField v-if="friend"
                  ref="input-ref"
                  :friendId="friend.id"
                  @pushBackMessage="handlePushBackMessage"
                  @appendToLastMessage="handleAppendToLastMessage"
                  @pushFrontMessage="handlePushFrontMessage"
      />
    </div>
  </dialog>
</template>

<style scoped>

</style>