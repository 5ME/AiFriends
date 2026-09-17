<script setup lang="ts">
import {computed, ref, watch} from "vue";
import api from "@/js/http/api";
import {isCurrentSample, playSample, stopCurrentSample} from "@/composables/useVoiceSample.js";

const props = defineProps(["voices", "curVoice"])
const myVoice = ref(props.curVoice)

watch(() => props.curVoice, newVal => {
  myVoice.value = newVal
})

const mineVoices = computed(() => props.voices.filter(v => v.is_mine))
const platformVoices = computed(() => props.voices.filter(v => !v.is_mine))

const STATUS_LABEL = { deploying: '审核中', rejected: '审核未通过' }

// 注意别叫 curVoice —— prop 已经叫 curVoice 了，同名两种含义（prop 是父组件传进来的当前值，
// 这里算的是按 myVoice 选中的那个对象），改名避免读代码时混淆。
const selectedVoice = computed(() => props.voices.find(v => v.id === myVoice.value))
const curProfile = computed(() => selectedVoice.value?.profile || '')
const curReady = computed(() => !selectedVoice.value || selectedVoice.value.status === 'ready')

const loading = ref(false)
const playing = ref(false)
const errorMessage = ref('')
let audioEl = null

// 用户切换下拉框时停掉正在播的试听并复位按钮：否则按钮会一直显示"停止"，
// 点一次只停掉旧的那段、要点第二次才听到新音色 —— 状态与所见不一致。
watch(myVoice, () => {
  stopCurrentSample()
  playing.value = false
})

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
        <optgroup v-if="mineVoices.length" label="我的音色">
          <option v-for="v in mineVoices" :key="v.id" :value="v.id">
            {{ v.name }}{{ STATUS_LABEL[v.status] ? '（' + STATUS_LABEL[v.status] + '）' : '' }}
          </option>
        </optgroup>
        <optgroup label="平台音色">
          <option v-for="v in platformVoices" :key="v.id" :value="v.id">
            {{ v.name }}
          </option>
        </optgroup>
      </select>
      <button type="button"
              data-test="voice-sample-btn"
              class="btn btn-outline"
              :disabled="loading || !myVoice || !curReady"
              :title="curReady ? (playing ? '停止试听' : '试听') : '该音色尚不可用'"
              @click="toggleSample">
        {{ loading ? '加载中' : (playing ? '停止' : '试听') }}
      </button>
    </div>
    <p v-if="curProfile" class="text-sm opacity-70 mt-1">{{ curProfile }}</p>
    <p v-if="!curReady" class="text-sm opacity-70 mt-1">该音色尚不可用，暂时无法试听</p>
    <p v-if="errorMessage" class="text-sm text-red-500 mt-1">{{ errorMessage }}</p>
  </fieldset>
</template>

<style scoped>

</style>
