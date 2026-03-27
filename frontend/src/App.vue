<script setup>

import NavBar from "@/components/navbar/NavBar.vue";
import {onMounted} from "vue";
import api from "@/js/http/api.js";
import {useUserStore} from "@/stores/user.js";
import {useRoute, useRouter} from "vue-router";

const user = useUserStore()
const route = useRoute()
const router = useRouter()

// 页面挂载时获取用户信息，防止刷新页面退出登录
onMounted(async () => {
  try {
    const response = await api.get('/api/user/account/get_user_info/')
    const data = response.data
    if (data.message === 'success') {
      user.setUserInfo(data)
    }
  } catch (e) {
    console.log(e)
  } finally {
    user.setHasPulledUserInfo(true)
    if (route.meta.needLogin && !user.isLogin()) {
      // 注意与 push 的区别
      await router.replace({name: 'user-account-login-index'})
    }
  }
})
</script>

<template>
  <NavBar>
    <RouterView/>
  </NavBar>
</template>

<style scoped>

</style>
