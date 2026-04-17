<script setup lang="ts">

import Photo from "@/views/create/character/components/Photo.vue";
import Name from "@/views/create/character/components/Name.vue";
import Profile from "@/views/create/character/components/Profile.vue";
import BackgroundImage from "@/views/create/character/components/BackgroundImage.vue";
import {onMounted, ref, useTemplateRef} from "vue";
import {base64ToFile} from "@/js/utils/base64_to_file";
import api from "@/js/http/api";
import {useRouter} from "vue-router";
import {useUserStore} from "@/stores/user";
import Voice from "@/views/create/character/components/Voice.vue";

const router = useRouter()
const user = useUserStore()

const photoRef = useTemplateRef('photo-ref')
const nameRef = useTemplateRef('name-ref')
const voiceRef = useTemplateRef('voice-ref')
const profileRef = useTemplateRef('profile-ref')
const backgroundImageRef = useTemplateRef('background-image-ref')

const errorMessage = ref('')

const voices = ref([])
const curVoiceId = ref(null)

onMounted(async () => {
  try {
    const response = await api.get('/api/create/character/voice/get_list/')
    const data = response.data
    if (data.message === "success") {
      voices.value = data.voices
      curVoiceId.value = data.voices[0].id
    }
  } catch (e) {
    console.log(e)
  }
})

async function handleCreate() {
  const photo = photoRef.value.myPhoto
  const name = nameRef.value.myName?.trim()
  const voice = voiceRef.value.myVoice
  const profile = profileRef.value.myProfile?.trim()
  const backgroundImage = backgroundImageRef.value.myBackgroundImage

  errorMessage.value = ''
  if (!photo) {
    errorMessage.value = '角色头像不能为空'
  } else if (!name) {
    errorMessage.value = '角色名称不能为空'
  } else if(!voice) {
    errorMessage.value = '角色音色不能为空'
  } else if (!profile) {
    errorMessage.value = '角色介绍不能为空'
  } else if (!backgroundImage) {
    errorMessage.value = '聊天背景不能为空'
  } else {
    const formData = new FormData()
    formData.append('name', name)
    formData.append('voice_id', voice)
    formData.append('profile', profile)
    formData.append('photo', base64ToFile(photo, 'photo.png'))
    formData.append('background_image', base64ToFile(backgroundImage, 'background_image.png'))

    try {
      const response = await api.post('api/create/character/create/', formData)
      const data = response.data
      if (data.message === 'success') {
        // 成功，跳转至个人主页
        await router.push({
          name: 'user-space-index',
          params: {
            user_id: user.id
          }
        })
      } else {
        errorMessage.value = data.message
      }
    } catch (e) {
      console.log(e)
    }
  }
}
</script>

<template>
  <div class="flex justify-center">
    <div class="card bg-base-200 w-120 shadow-md mt-5">
      <div class="card-body flex justify-center">
        <h3 class="card-title flex justify-center">
          创建角色
        </h3>
        <Photo ref="photo-ref"/>
        <Name ref="name-ref"/>
        <Voice ref="voice-ref" :voices="voices" :curVoiceId="curVoiceId"/>
        <Profile ref="profile-ref"/>
        <BackgroundImage ref="background-image-ref"/>

        <p v-if="errorMessage" class="text-sm text-red-500">{{ errorMessage }}</p>

        <div class="card-actions justify-center mt-3">
          <button @click="handleCreate" class="btn btn-neutral w-50">
            创建
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>

</style>