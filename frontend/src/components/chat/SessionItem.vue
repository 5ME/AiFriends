<script setup lang="ts">
defineProps(['session', 'active'])
const emits = defineEmits(['select'])
</script>

<template>
  <button type="button"
          class="w-full h-16 flex items-center gap-3 rounded-xl px-2 pl-1 text-left transition-colors cursor-pointer
                 hover:bg-base-300"
          :class="active ? 'session-active' : 'session-inactive'"
          :aria-current="active ? 'true' : undefined"
          @click="emits('select', session.character.id)">
    <div class="avatar shrink-0">
      <div class="w-10 rounded-full">
        <img :src="session.character.photo" alt="" />
      </div>
    </div>
    <span class="text-base font-medium line-clamp-1 break-all">
      {{ session.character.name }}
    </span>
  </button>
</template>

<style scoped>
</style>
