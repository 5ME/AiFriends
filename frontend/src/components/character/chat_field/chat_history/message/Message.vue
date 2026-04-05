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
      <div class="chat-bubble whitespace-pre-wrap">
        {{ message.content }}
      </div>
      <!--<div class="chat-footer opacity-50">Delivered</div>-->
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
      <div class="chat-bubble chat-bubble-success whitespace-pre-wrap">
        {{ message.content }}
      </div>
      <!--<div class="chat-footer opacity-50">Seen at 12:46</div>-->
    </div>
  </div>
</template>

<style scoped>

</style>