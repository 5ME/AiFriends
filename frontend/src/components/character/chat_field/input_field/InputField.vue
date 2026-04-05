<script setup lang="ts">

import MicIcon from "@/components/character/icons/MicIcon.vue";
import SendIcon from "@/components/character/icons/SendIcon.vue";
import streamApi from "@/js/http/streamApi";
import {ref, useTemplateRef} from "vue";

const props = defineProps(['friendId'])
const emits = defineEmits(['pushBackMessage', 'appendToLastMessage'])

const inputRef = useTemplateRef('input-ref')
const message = ref('')
let isProcessing = false

function focus() {
  inputRef.value.focus()
}

async function handleSend() {
  if (isProcessing) {
    return
  }
  isProcessing = true

  const content = message.value.trim()
  if (!console) {
    return
  }
  message.value = ''

  emits('pushBackMessage', {
    role: 'user',
    content: content,
    id: crypto.randomUUID()
  })
  emits('pushBackMessage', {
    role: 'ai',
    content: '',
    id: crypto.randomUUID()
  })

  try {
    await streamApi('/api/friend/message/chat/', {
      body: {
        friend_id: props.friendId,
        message: content
      },
      onmessage(data, isDone) {
        if (isDone) {
          isProcessing = false
        } else if (data.content) {
          emits('appendToLastMessage', data.content)
        }
      },
      onerror(err) {
        isProcessing = false
        console.log(err)
      },
    })
  } catch (e) {
    console.log(e)
    isProcessing = false
  }
}

defineExpose({focus,})
</script>

<template>
  <form @submit.prevent="handleSend" class="absolute bottom-4 left-2 h-12 w-86 flex items-center">
    <input class="input bg-black/30 backdrop-blur text-base text-white w-full h-full rounded-md pr-20"
           type="text" placeholder=""
           ref="input-ref" v-model="message"/>
    <div class="absolute right-2 w-8 h-8 flex justify-center items-center cursor-pointer"
         @click="handleSend">
      <SendIcon/>
    </div>
    <div class="absolute right-10 w-8 h-8 flex justify-center items-center cursor-pointer">
      <MicIcon/>
    </div>
  </form>
</template>

<style scoped>

</style>