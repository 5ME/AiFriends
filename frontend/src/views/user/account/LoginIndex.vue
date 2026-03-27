<script setup lang="ts">
import api from "@/js/http/api";
import {useUserStore} from "@/stores/user";
import {ref} from "vue";
import {useRouter} from "vue-router";

const username = ref('')
const password = ref('')
const errorMessage = ref('')

const user = useUserStore()
const router = useRouter()

async function handleLogin() {
  console.log("handle login request...")
  errorMessage.value = ''
  if (!username.value.trim()) {
    errorMessage.value = '用户名不能为空'
  } else if (!password.value.trim()) {
    errorMessage.value = '密码不能为空'
  } else {
    try {
      const response = await api.post('/api/user/account/login/', {
        'username': username.value,
        'password': password.value
      })
      const data = response.data
      if (data.message === 'success') {
        user.setAccessToken(data.access_token)
        user.setUserInfo(data)
        await router.push({
          name: 'homepage-index'
        })
      } else {
        console.log(data.message)
        errorMessage.value = data.message
      }
    } catch (e) {
      console.log(e)
    }
  }
}
</script>

<template>
  <div class="flex justify-center mt-50">
    <form @submit.prevent="handleLogin" class="fieldset bg-base-200 border-base-300 rounded-box w-xs border p-4">
      <label class="label">用户名</label>
      <input v-model="username" type="text" class="input" placeholder="用户名"/>

      <label class="label">密码</label>
      <input v-model="password" type="password" class="input" placeholder="密码"/>

      <p v-if="errorMessage" class="text-sm text-red-600">{{ errorMessage }}</p>

      <button class="btn btn-neutral mt-4">登录</button>

      <div class="flex justify-end">
        <RouterLink :to="{name: 'user-account-register-index'}" class="btn btn-sm btn-ghost text-gray-500">
          立即注册
        </RouterLink>
      </div>
    </form>
  </div>
</template>

<style scoped>

</style>