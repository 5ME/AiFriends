<script setup lang="ts">
import {useUserStore} from '@/stores/user';

const props = defineProps(['message', 'character'])

const user = useUserStore()
</script>

<template>
  <div v-if="message.content">
    <!--AI的话-->
    <div v-if="message.role === 'ai'" class="chat chat-start">
      <div class="chat-image avatar">
        <div class="w-10 rounded-full">
          <img :src="character.photo" alt=""/>
        </div>
      </div>
      <div class="chat-header">
        {{ character.name }}
        <!--<time class="text-xs opacity-50">12:45</time>-->
      </div>
      <div class="chat-bubble whitespace-pre-wrap break-all">
        {{ message.content }}
      </div>
    </div>

    <!--RAG 引用来源：独立于聊天气泡，避免挤压消息空间-->
    <div v-if="message.role === 'ai' && message.citations?.length"
         class="collapse collapse-arrow ml-14 mt-0.5 w-fit max-w-80
                bg-base-200/50 rounded-box">
      <input type="checkbox" />
      <div class="collapse-title text-xs font-medium opacity-60">
        📖 {{ message.citations.length }} 条参考来源
      </div>
      <div class="collapse-content text-xs opacity-50">
        <p v-for="c in message.citations" :key="c.index" class="py-0.5">
          {{ c.index }}. {{ c.title || '系统知识库' }}
        </p>
      </div>
    </div>

    <!--用户的话-->
    <div v-else-if="message.role === 'user'" class="chat chat-end">
      <div class="chat-image avatar">
        <div class="w-10 rounded-full">
          <img :src="user.photo" alt=""/>
        </div>
      </div>
      <div class="chat-header">
        {{ user.username }}
        <!--<time class="text-xs opacity-50">12:46</time>-->
      </div>
      <div class="chat-bubble chat-bubble-success whitespace-pre-wrap break-all">
        {{ message.content }}
      </div>
      <!--<div class="chat-footer opacity-50">Seen at 12:46</div>-->
    </div>
  </div>
</template>

<style scoped>

</style>