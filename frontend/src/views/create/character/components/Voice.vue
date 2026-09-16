<script setup lang="ts">
import {ref, watch} from "vue";

const props = defineProps(["voices", "curVoice"])
const myVoice = ref(props.curVoice)

watch(() => props.curVoice, newVal => {
  myVoice.value = newVal
})

defineExpose({
  myVoice
})
</script>

<template>
  <fieldset class="fieldset">
    <legend class="fieldset-legend">音色</legend>
    <select v-model="myVoice" class="select w-108">
      <option v-for="voice in voices" :key="voice.id" :value="voice.id">
        {{ voice.name }}
      </option>
    </select>
  </fieldset>
</template>

<style scoped>

</style>