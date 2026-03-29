<script setup lang="ts">
import {ref, watch} from "vue";

const props = defineProps(['profile'])
const myProfile = ref(props.profile)

watch(() => props.profile, newVal => {
  myProfile.value = newVal
})

defineExpose({
  myProfile,
})
</script>

<template>
  <fieldset class="fieldset">
    <legend class="fieldset-legend">角色介绍</legend>
    <textarea v-model="myProfile" rows="5" class="textarea w-108"
              placeholder="介绍一下你创建的角色吧"/>
  </fieldset>
</template>

<style scoped>

</style>