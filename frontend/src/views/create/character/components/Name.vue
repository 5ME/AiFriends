<script setup lang="ts">
import {ref, watch} from "vue";

const props = defineProps(['name'])
const myName = ref(props.name)

watch(() => props.name, newVal => {
  myName.value = newVal
})

defineExpose({
  myName,
})
</script>

<template>
  <fieldset class="fieldset">
    <legend class="fieldset-legend">角色名称</legend>
    <label class="input w-108">
      <input v-model="myName"
             type="text"
             placeholder="有趣的角色从名字开始~"
             minlength="1"
             maxlength="30"
      />
    </label>
  </fieldset>
</template>

<style scoped>

</style>