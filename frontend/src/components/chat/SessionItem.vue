<script setup lang="ts">
defineProps(['session', 'active'])
const emits = defineEmits(['select'])
</script>

<template>
  <button type="button"
          class="w-full h-16 flex items-center gap-3 rounded-xl px-2 text-left transition-colors
                 hover:bg-base-300"
          :class="active
            ? 'bg-primary/10 border-l-4 border-primary pl-1'
            : 'border-l-4 border-transparent pl-1'"
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
