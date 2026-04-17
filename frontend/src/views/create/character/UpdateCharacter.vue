<script setup lang="ts">

import Photo from "@/views/create/character/components/Photo.vue";
import Name from "@/views/create/character/components/Name.vue";
import Profile from "@/views/create/character/components/Profile.vue";
import BackgroundImage from "@/views/create/character/components/BackgroundImage.vue";
import {onMounted, ref, useTemplateRef, watch} from "vue";
import {base64ToFile} from "@/js/utils/base64_to_file";
import api from "@/js/http/api";
import {useRoute, useRouter} from "vue-router";
import {useUserStore} from "@/stores/user";
import Voice from "@/views/create/character/components/Voice.vue";

const router = useRouter()
const user = useUserStore()
const route = useRoute()

const character = ref(null)
const voices = ref([])
const curVoiceId = ref(null)

async function getCharacterData() {
  try {
    const response = await api.get('api/create/character/get_single/', {
      params: {character_id: route.params.character_id}
    })
    const data = response.data
    if (data.message === 'success') {
      character.value = data.character
      voices.value = data.voices
      curVoiceId.value = data.character.voice_id
    }
  } catch (e) {
    console.log(e)
  }
}

onMounted(async () => {
  await getCharacterData()
})

watch(() => route.params.character_id, async () => {
  character.value = null
  await getCharacterData()
})

const photoRef = useTemplateRef('photo-ref')
const nameRef = useTemplateRef('name-ref')
const voiceRef = useTemplateRef('voice-ref')
const profileRef = useTemplateRef('profile-ref')
const backgroundImageRef = useTemplateRef('background-image-ref')

const errorMessage = ref('')

async function handleUpdate() {
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
  } else if (!voice) {
    errorMessage.value = '角色音色不能为空'
  } else if (!profile) {
    errorMessage.value = '角色介绍不能为空'
  } else if (!backgroundImage) {
    errorMessage.value = '聊天背景不能为空'
  } else {
    const formData = new FormData()
    formData.append('character_id', route.params.character_id as string)
    formData.append('name', name)
    formData.append('voice_id', voice)
    formData.append('profile', profile)
    if (photo !== character.value.photo) {
      formData.append('photo', base64ToFile(photo, 'photo.png'))
    }
    if (backgroundImage !== character.value.background_image) {
      formData.append('background_image', base64ToFile(backgroundImage, 'background_image.png'))
    }

    try {
      const response = await api.post('api/create/character/update/', formData)
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
  <div v-if="character" class="flex justify-center">
    <div class="card bg-base-200 w-120 shadow-md mt-10">
      <div class="card-body flex justify-center">
        <h3 class="card-title flex justify-center">
          修改角色
        </h3>
        <Photo ref="photo-ref" :photo="character.photo"/>
        <Name ref="name-ref" :name="character.name"/>
        <Voice ref="voice-ref" :voices="voices" :curVoiceId="curVoiceId"/>
        <Profile ref="profile-ref" :profile="character.profile"/>
        <BackgroundImage ref="background-image-ref" :backgroundImage="character.background_image"/>

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