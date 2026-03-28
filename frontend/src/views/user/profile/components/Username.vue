<script setup lang="ts">
import {ref, watch} from "vue";

const props = defineProps(['username'])
const myUsername = ref(props.username)

watch(() => props.username, newVal => {
  myUsername.value = newVal
})

defineExpose({
  myUsername,
})
</script>

<template>
  <fieldset class="fieldset">
    <legend class="fieldset-legend">用户名</legend>
    <label class="input w-108">
      <input v-model="myUsername"
             type="text"
             placeholder="用户名"
             minlength="3"
             maxlength="30"
      />
    </label>
  </fieldset>
</template>

<style scoped>

</style>