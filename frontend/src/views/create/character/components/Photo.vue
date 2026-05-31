<script setup lang="ts">
import {nextTick, onBeforeUnmount, ref, useTemplateRef, watch} from "vue";
import CameraIcon from "@/views/user/profile/components/icons/CameraIcon.vue";
import { useImageCropper } from '@/composables/useImageCropper.js'

const props = defineProps(['photo'])
const myPhoto = ref(props.photo)

watch(() => props.photo, newVal => {
  myPhoto.value = newVal
})

const fileInputRef = useTemplateRef('file-input-ref')
const modalRef = useTemplateRef('modal-ref')
const croppieRef = useTemplateRef('croppie-ref')

const { init: initCroppie, crop: doCrop, destroy: destroyCroppie } = useImageCropper({
  viewportWidth: 200,
  viewportHeight: 200,
  viewportType: 'square',
  boundaryWidth: 300,
  boundaryHeight: 300,
})

async function openModal(photo) {
  modalRef.value.showModal()
  await nextTick()
  initCroppie(croppieRef.value, photo)
}

async function crop() {
  const result = await doCrop()
  if (result) {
    myPhoto.value = result
  }
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
  destroyCroppie()
})

defineExpose({
  myPhoto,
})
</script>

<template>
  <fieldset class="fieldset">
    <!--头像展示-->
    <legend class="fieldset-legend">头像</legend>
    <div class="flex justify-center">
      <div class="avatar relative">
        <div v-if="myPhoto" class="w-25 rounded-full">
          <img :src="myPhoto" alt="avatar"/>
        </div>
        <div v-else class="w-25 h-25 rounded-full bg-base-200"></div>
        <div class="absolute left-0 top-0 w-25 h-25 flex justify-center items-center
                  bg-black/20 rounded-full cursor-pointer"
             @click="fileInputRef.click()">
          <CameraIcon/>
        </div>
      </div>
    </div>

    <!--上传图片-->
    <input ref="file-input-ref" type="file"
           accept=".jpg, .jpeg, .png, image/jpeg, image/png"
           class="hidden"
           @change="onFileChange">

    <!--模态框-->
    <dialog ref="modal-ref" id="my_modal_2" class="modal">
      <div class="modal-box transition-none">
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