<script setup lang="ts">
import {useTemplateRef} from "vue";
import CharacterDetail from "@/components/character/CharacterDetail.vue";

defineProps(['character'])

const characterDetailRef = useTemplateRef('character-detail-ref')

function handleAvatarClick() {
  characterDetailRef.value.showModal()
}
</script>

<template>
  <button type="button"
          class="h-10 w-fit rounded-full glass-panel flex items-center gap-2 px-2 cursor-pointer chat-ring"
          :aria-label="`查看${character.name}的详情`"
          @click="handleAvatarClick">
    <div class="avatar">
      <div class="w-8 rounded-full">
        <img :src="character.photo" alt="">
      </div>
    </div>
    <div class="chat-text text-sm line-clamp-1 break-all">
      {{ character.name }}
    </div>
  </button>

  <CharacterDetail ref="character-detail-ref" :character="character" mode="chat"/>
</template>

<style scoped>

</style>
