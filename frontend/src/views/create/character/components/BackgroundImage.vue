<script setup lang="ts">
import {nextTick, onBeforeUnmount, ref, useTemplateRef, watch} from "vue";
import CameraIcon from "@/views/user/profile/components/icons/CameraIcon.vue";
import Croppie from "croppie"
import 'croppie/croppie.css'

const props = defineProps(['backgroundImage'])
const myBackgroundImage = ref(props.backgroundImage)

watch(() => props.backgroundImage, newVal => {
  myBackgroundImage.value = newVal
})

const fileInputRef = useTemplateRef('file-input-ref')
const modalRef = useTemplateRef('modal-ref')
const croppieRef = useTemplateRef('croppie-ref')
let croppie = null

async function openModal(photo) {
  modalRef.value.showModal()
  await nextTick()
  if (!croppie) {
    croppie = new Croppie(croppieRef.value, {
      viewport: {width: 300, height: 500},
      boundary: {width: 600, height: 600},
      enableOrientation: true,
      enforceBoundary: true,
    })
  }
  croppie.bind({
    url: photo,
  })
}

async function crop() {
  if (!croppie)
    return
  myBackgroundImage.value = await croppie.result({
    type: 'base64',
    size: 'viewport',
  })
  modalRef.value.close()
}

function onFileChange(e) {
  const file = e.target.files[0]
  e.target.value = ''
  if (!file) {
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    openModal(reader.result)
  }
  reader.readAsDataURL(file)
}

onBeforeUnmount(() => {
  croppie?.destroy()
})

defineExpose({
  myBackgroundImage,
})
</script>

<template>
  <fieldset class="fieldset">
    <legend class="fieldset-legend">聊天背景</legend>
    <div class="avatar relative">
      <div v-if="myBackgroundImage" class="w-15 h-25 rounded-box">
        <img :src="myBackgroundImage" alt="聊天背景">
      </div>
      <div v-else class="w-15 h-25 rounded-box bg-base-200"></div>
      <div class="w-15 h-25 rounded-box absolute left-0 top-0 bg-black/20
                  flex justify-center items-center cursor-pointer"
           @click="fileInputRef.click()">
        <CameraIcon/>
      </div>
    </div>

    <input ref="file-input-ref" type="file"
           accept=".jpg, .jpeg, .png, image/jpeg, image/png"
           class="hidden"
           @change="onFileChange">

    <!--模态框-->
    <dialog ref="modal-ref" id="my_modal_2" class="modal">
      <div class="modal-box transition-none max-w-2xl">
        <form method="dialog">
          <button class="btn btn-sm btn-circle btn-ghost absolute right-2 top-2">✕</button>
        </form>
        <!-- croppie绑定的标签 -->
        <div ref="croppie-ref" class="flex flex-col justify-center my-4"></div>
        <div class="modal-action">
          <button @click="modalRef.close()" class="btn">取消</button>
          <button @click="crop" class="btn btn-neutral">确定</button>
        </div>
      </div>
    </dialog>
  </fieldset>
</template>

<style scoped>

</style>