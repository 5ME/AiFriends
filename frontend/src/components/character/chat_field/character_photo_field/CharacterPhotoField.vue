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
  <div class="h-10 w-fit rounded-full bg-black/50 flex items-center gap-2 px-2 cursor-pointer"
       @click="handleAvatarClick">
    <div class="avatar">
      <div class="w-8 rounded-full">
        <img :src="character.photo" alt="">
      </div>
    </div>
    <div class="text-white text-sm line-clamp-1 break-all">
      {{ character.name }}
    </div>
  </div>

  <CharacterDetail ref="character-detail-ref" :character="character" mode="chat"/>
</template>

<style scoped>

</style>
