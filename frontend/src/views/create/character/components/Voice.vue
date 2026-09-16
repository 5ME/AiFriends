<script setup lang="ts">
import {computed, ref, watch} from "vue";
import api from "@/js/http/api";
import {isCurrentSample, playSample, stopCurrentSample} from "@/composables/useVoiceSample.js";

const props = defineProps(["voices", "curVoice"])
const myVoice = ref(props.curVoice)

watch(() => props.curVoice, newVal => {
  myVoice.value = newVal
})

const curProfile = computed(() => {
  const v = props.voices.find(v => v.id === myVoice.value)
  return v?.profile || ''
})

const loading = ref(false)
const playing = ref(false)
const errorMessage = ref('')
let audioEl = null

async function toggleSample() {
  if (playing.value) {
    stopCurrentSample()
    playing.value = false
    return
  }
  errorMessage.value = ''
  loading.value = true
  try {
    const response = await api.get('/api/create/character/voice/sample/', {
      params: {voice: myVoice.value},
    })
    audioEl = playSample(response.data.url)
    playing.value = true
    audioEl.onended = () => {
      if (isCurrentSample(audioEl)) playing.value = false
    }
    audioEl.onerror = () => {
      playing.value = false
      errorMessage.value = '试听失败，请稍后再试'
    }
  } catch (e) {
    errorMessage.value = '试听失败，请稍后再试'
  } finally {
    loading.value = false
  }
}

defineExpose({
  myVoice
})
</script>

<template>
  <fieldset class="fieldset">
    <legend class="fieldset-legend">音色</legend>
    <div class="flex items-center gap-2">
      <select v-model="myVoice" class="select w-96">
        <option v-for="voice in voices" :key="voice.id" :value="voice.id">
          {{ voice.name }}
        </option>
      </select>
      <button type="button"
              data-test="voice-sample-btn"
              class="btn btn-outline"
              :disabled="loading || !myVoice"
              :title="playing ? '停止试听' : '试听'"
              @click="toggleSample">
        {{ loading ? '加载中' : (playing ? '停止' : '试听') }}
      </button>
    </div>
    <p v-if="curProfile" class="text-sm opacity-70 mt-1">{{ curProfile }}</p>
    <p v-if="errorMessage" class="text-sm text-red-500 mt-1">{{ errorMessage }}</p>
  </fieldset>
</template>

<style scoped>

</style>
