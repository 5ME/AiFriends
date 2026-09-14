// 简约背景开关（4B D4B-3：**每角色独立**）。
// 存 localStorage：{"<character_id>": true}。键名与值都做校验——脏数据一律忽略，
// 任何存储异常都不得影响聊天页渲染（E1）。
//
// ⚠️ 响应式关键：状态必须落在**模块级 ref**（与既有 useVoiceToggle / useToast 同惯例）。
// 若写成 computed(() => loadChatBgMap()[key]) —— 读取 localStorage 不是响应式依赖，
// computed 缓存后**永不失效**，表现为"点了开关没反应"。评审探针已复现该缺陷。
import { computed, ref, watch } from 'vue'

export const STORAGE_KEY = 'chatSimpleBg'

/** 解析存储值：只接受 {"<数字id>": boolean} 形状，其余丢弃 */
export function parseChatBg(raw) {
  try {
    const parsed = JSON.parse(raw ?? '')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const out = {}
    for (const [k, v] of Object.entries(parsed)) {
      if (typeof v === 'boolean' && /^\d+$/.test(k)) out[k] = v
    }
    return out
  } catch {
    return {}
  }
}

export function loadChatBgMap() {
  try {
    return parseChatBg(window.localStorage.getItem(STORAGE_KEY))
  } catch {
    return {}
  }
}

export function saveChatBgMap(map) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(map))
  } catch {
    // 隐私模式/配额耗尽：静默降级为内存态
  }
}

// 模块级单例：启动读一次，之后每次变更持久化（deep 覆盖 future 的嵌套写）。
// flush:'sync' 是必须的——默认异步批次下，setSimple 之后到下一次 flush 之间
// 用户若立刻关页面/刷新，偏好会丢（TDD 写测试时实测到）。
const state = ref(loadChatBgMap())
watch(state, (v) => saveChatBgMap(v), { deep: true, flush: 'sync' })

/** 仅供测试：把模块状态重新对回存储（单测里清空 localStorage 后必须调用，
 *  否则上一用例的内存态会污染下一用例——模块状态只在首次 import 时读一次） */
export function __resetChatBgState() {
  state.value = loadChatBgMap()
}

/** @param {number|string} characterId */
export function useChatBg(characterId) {
  const key = String(characterId)
  const simpleOn = computed(() => state.value[key] === true)

  function setSimple(on) {
    state.value = { ...state.value, [key]: !!on }
  }

  return { simpleOn, setSimple, toggleSimple: () => setSimple(!simpleOn.value) }
}
