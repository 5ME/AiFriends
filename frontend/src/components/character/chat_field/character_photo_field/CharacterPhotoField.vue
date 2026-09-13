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
  <!-- 提示：<button> 内不得再嵌套交互元素；若日后需要在 pill 内加次级按钮，必须拆分结构 -->
  <button type="button"
          class="h-10 w-fit rounded-full bg-black/50 flex items-center gap-2 px-2 cursor-pointer
                 focus-visible:ring-2 ring-white/40 outline-none"
          :aria-label="`查看 ${character.name} 的角色详情`"
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
