<script setup lang="ts">
import {useRoute, useRouter} from "vue-router";

const route = useRoute()
// 注意与下面这行区分，两者用处不一样
// const router = useRouter()
</script>

<template>
  空间：{{ route.params.user_id }}
</template>

<style scoped>

</style>