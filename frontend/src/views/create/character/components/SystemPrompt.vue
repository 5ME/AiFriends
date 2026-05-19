<script setup lang="ts">
import {ref, watch} from "vue";

const props = defineProps(['systemPrompt'])
const myValue = ref(props.systemPrompt)

watch(() => props.systemPrompt, newVal => {
  myValue.value = newVal
})

defineExpose({myValue})
</script>

<template>
  <fieldset class="fieldset">
    <legend class="fieldset-legend">角色信息（发送给 AI）</legend>
    <textarea v-model="myValue" rows="8" class="textarea w-108"
              placeholder="详细的角色性格、语气、行为规则等，将发送给 AI 作为系统提示词"/>
  </fieldset>
</template>
