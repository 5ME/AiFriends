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
  <!-- Phase 4 无障碍：原为 <div @click>（键盘不可达）+ <img alt="">（无替代文本）→ 真按钮 + 补 alt -->
  <button type="button"
          class="h-10 w-fit rounded-full bg-black/50 flex items-center gap-2 px-2 cursor-pointer
                 focus-visible:ring-2 ring-white/40"
          aria-label="查看角色详情"
          @click="handleAvatarClick">
    <div class="avatar">
      <div class="w-8 rounded-full">
        <img :src="character.photo" :alt="`${character.name}的头像`">
      </div>
    </div>
    <div class="text-white text-sm line-clamp-1 break-all">
      {{ character.name }}
    </div>
  </button>

  <CharacterDetail ref="character-detail-ref" :character="character" mode="chat"/>
</template>

<style scoped>

</style>
