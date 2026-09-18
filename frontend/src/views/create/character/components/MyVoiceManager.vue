<script setup lang="ts">
import {computed, onUnmounted, ref, watch} from "vue";
import api from "@/js/http/api";

const props = defineProps(["voices"])
const emit = defineEmits(["changed"])

const STATUS_LABEL = {deploying: '审核中', rejected: '审核未通过', ready: '可用'}
const MAX_BYTES = 8 * 1024 * 1024
const ALLOWED = ['mp3', 'wav', 'm4a']
const POLL_INTERVAL_MS = 30000
const MAX_POLLS = 20             // 30s × 20 = 10 分钟；到点停手并让用户自己刷新

const myVoices = computed(() => props.voices.filter(v => v.is_mine))

// 有审核中的音色就每 30 秒让父组件重拉一次列表，全部落地即停 —— 否则用户得手动刷新页面
// 才能看到「可用」（阿里云侧实测约 15 秒出结果，而 Beat 是 5 分钟节奏，之间靠这里兜住）。
// ⚠️ 带上限是复用 `useDocumentPolling` 的完整写法：spec 风险 9 描述过"音色长期停在
// deploying"（Beat 只扫 24 小时内的行），没有上限就会无限轮询、而且不给用户任何交代。
let pollTimer = null
let pollCount = 0

const pollExhausted = ref(false)

const deployingCount = computed(
  () => myVoices.value.filter(v => v.status === 'deploying').length)

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

watch(deployingCount, (n) => {
  stopPolling()
  pollCount = 0
  pollExhausted.value = false
  if (n > 0) {
    pollTimer = setInterval(() => {
      pollCount += 1
      if (pollCount > MAX_POLLS) {
        stopPolling()
        pollExhausted.value = true
        return
      }
      emit('changed')
    }, POLL_INTERVAL_MS)
  }
}, {immediate: true})

onUnmounted(stopPolling)

const open = ref(false)
const sampleFile = ref(null)
const name = ref('')
const profile = ref('')
const consent = ref(false)
const errorMessage = ref('')
const submitting = ref(false)

function onFileChange(e) {
  sampleFile.value = e.target.files?.[0] || null
  errorMessage.value = ''
}

function validate() {
  if (!name.value.trim()) return '请填写音色名称'
  if (!sampleFile.value) return '请选择声音样本'
  const suffix = (sampleFile.value.name.split('.').pop() || '').toLowerCase()
  if (!ALLOWED.includes(suffix)) return '样本格式只支持 mp3 / wav / m4a'
  if (sampleFile.value.size > MAX_BYTES) return '样本不得超过 8MB'
  if (!consent.value) return '请先勾选授权声明：这是本人声音，或已获得声音权利人授权'
  return ''
}

async function submit() {
  const msg = validate()
  if (msg) {
    errorMessage.value = msg
    return
  }
  submitting.value = true
  errorMessage.value = ''
  try {
    const fd = new FormData()
    fd.append('file', sampleFile.value)
    fd.append('name', name.value.trim())
    fd.append('profile', profile.value.trim())
    fd.append('consent', 'true')
    await api.post('/api/create/character/voice/clone/', fd)
    sampleFile.value = null
    name.value = ''
    profile.value = ''
    consent.value = false
    emit('changed')
  } catch (e) {
    errorMessage.value = e.response?.data?.message || '复刻失败，请稍后再试'
  } finally {
    submitting.value = false
  }
}

async function remove(voice) {
  if (!confirm(`确定删除音色「${voice.name}」吗？`)) return
  errorMessage.value = ''
  try {
    await api.post('/api/create/character/voice/remove/', {voice: voice.id})
    emit('changed')
  } catch (e) {
    errorMessage.value = e.response?.data?.message || '删除失败，请稍后再试'
  }
}
</script>

<template>
  <fieldset class="fieldset">
    <legend class="fieldset-legend">我的音色</legend>

    <template v-if="myVoices.length">
      <div v-for="v in myVoices" :key="v.id"
           class="flex items-center justify-between gap-2 py-1">
        <span class="text-sm">
          {{ v.name }}
          <span class="opacity-70">（{{ STATUS_LABEL[v.status] }}）</span>
        </span>
        <button type="button" class="btn btn-xs btn-outline"
                :data-test="`voice-remove-${v.id}`"
                @click="remove(v)">删除</button>
      </div>
    </template>

    <button type="button" class="btn btn-sm btn-outline w-fit mt-1"
            data-test="toggle-upload" @click="open = !open">
      {{ open ? '收起' : '创建我的音色' }}
    </button>

    <div v-if="open" class="mt-2 flex flex-col gap-2">
      <input type="file" accept=".mp3,.wav,.m4a" class="file-input file-input-bordered w-full"
             data-test="sample-input" @change="onFileChange"/>
      <p class="text-xs opacity-70">
        支持 mp3 / wav / m4a，建议 10~20 秒的清晰朗读，不超过 8MB
      </p>
      <input v-model="name" type="text" placeholder="音色名称（必填）"
             class="input input-bordered w-full" data-test="voice-name-input"/>
      <input v-model="profile" type="text" placeholder="音色描述（可选）"
             class="input input-bordered w-full" data-test="voice-profile-input"/>

      <!-- 隐私说明必须如实：样本会提交给语音合成服务方；阿里云侧仍留有原始样本
           （实测 query_voice 能返回 resource_link），所以不能写"全链路已删除" -->
      <label class="flex items-start gap-2 text-sm cursor-pointer">
        <input v-model="consent" type="checkbox" class="checkbox checkbox-sm mt-0.5"
               data-test="consent-checkbox"/>
        <span>
          我确认这是<b>本人声音</b>，或已获得声音权利人授权。
          <span class="opacity-70">
            样本会被提交给语音合成服务方用于复刻，复刻完成后我们会立即删除。
          </span>
        </span>
      </label>

      <button type="button" class="btn btn-sm btn-neutral w-fit"
              data-test="clone-submit" :disabled="submitting" @click="submit">
        {{ submitting ? '提交中' : '提交复刻' }}
      </button>
    </div>

    <p v-if="pollExhausted" class="text-xs opacity-70 mt-1">
      审核耗时较长，稍后刷新页面查看结果
    </p>
    <p v-if="errorMessage" class="text-sm text-red-500 mt-1">{{ errorMessage }}</p>
  </fieldset>
</template>

<style scoped>

</style>
