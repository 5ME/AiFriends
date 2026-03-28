<script setup lang="ts">

import Photo from "@/views/user/profile/components/Photo.vue";
import Username from "@/views/user/profile/components/Username.vue";
import Profile from "@/views/user/profile/components/Profile.vue";
import {useUserStore} from "@/stores/user";
import {ref, useTemplateRef} from "vue";
import {base64ToFile} from "@/js/utils/base64_to_file";
import api from "@/js/http/api";

const user = useUserStore()

const photoRef = useTemplateRef('photo-ref')
const usernameRef = useTemplateRef('username-ref')
const profileRef = useTemplateRef('profile-ref')
const errorMessage = ref('')

async function handleUpdate() {
  const photo = photoRef.value.myPhoto
  const username = usernameRef.value.myUsername.trim()
  const profile = profileRef.value.myProfile.trim()

  errorMessage.value = ''
  if (!photo) {
    errorMessage.value = '头像不能为空'
  } else if (!username) {
    errorMessage.value = '用户名不能为空'
  } else if (!profile) {
    errorMessage.value = '简介不能为空'
  } else {
    const formData = new FormData()
    formData.append('username', username)
    formData.append('profile', profile)
    if (photo !== user.photo) {
      formData.append('photo', base64ToFile(photo, 'photo.png'))
    }
    try {
      const res = await api.post('/api/user/profile/update/', formData)
      const data = res.data
      if (data.message === 'success') {
        user.setUserInfo(data)
      } else {
        errorMessage.value = data.message
      }
    } catch (err) {
      console.log(err)
    }
  }
}
</script>

<template>
  <div class="flex justify-center">
    <div class="card bg-base-200 w-120 shadow-md mt-20">
      <div class="card-body flex justify-center">
        <h3 class="card-title flex justify-center">
          编辑资料
        </h3>
        <Photo ref="photo-ref" :photo="user.photo"/>
        <Username ref="username-ref" :username="user.username"/>
        <Profile ref="profile-ref" :profile="user.profile"/>

        <p v-if="errorMessage" class="text-sm text-red-500">{{ errorMessage }}</p>

        <div class="card-actions justify-center mt-3">
          <button @click="handleUpdate" class="btn btn-neutral w-50">
            保存
          </button>
        </div>
      </div>
    </div>
  </div>

</template>

<style scoped>

</style>