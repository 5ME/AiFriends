// 会话栏「最后一条消息」预览的**本地覆盖层**（M 档）。
// 服务端权威数据来自 `GET /api/friend/get_list/` 的 last_message / last_message_at；
// 这里只承载"刚发生、还没被下一次拉取覆盖"的乐观更新，键为 Friend 主键（session.id）。
//
// ⚠️ 状态必须落在模块级 reactive（与 useChatBg / useToast 同惯例）：会话栏与聊天窗
// 是 ChatIndex 下的两棵兄弟子树，跨子树共享只能靠模块级单例。
import { reactive, ref } from 'vue'

const previews = reactive({})   // { '<friendId>': { text, at } }
const latestId = ref(null)      // 最近一次更新的 friendId（字符串），会话栏据此置顶

/** 仅供测试：清空模块状态（模块状态跨用例存活，不重置会污染下一用例） */
export function __resetSessionPreview() {
  for (const key of Object.keys(previews)) delete previews[key]
  latestId.value = null
}

/**
 * 写入本地预览。文本为空串时应由调用方跳过（保留上一条，别把预览刷成空白）。
 * @param {number|string} friendId Friend 主键
 * @param {{text?: string, at?: string|Date}} payload at 缺省为当前时间
 */
export function setPreview(friendId, { text, at = new Date().toISOString() } = {}) {
  const key = String(friendId)
  previews[key] = { text: text == null ? '' : String(text), at }
  latestId.value = key
}

export function useSessionPreview() {
  return { previews, latestId, setPreview }
}

/**
 * 把命中的会话提到最前（与服务端 last_active 排序保持一致，避免"刷新后它自己跳上去"）。
 * 纯函数：未命中或已在首位时原样返回**同一个引用**，不触发无意义的重渲染。
 * 键规则与 previews 一致（统一 String）——接口给 number、存储键是 string。
 * @param {Array<{id: number|string}>} list
 * @param {number|string} friendId
 * @returns {Array}
 */
export function promote(list, friendId) {
  const idx = list.findIndex((s) => String(s.id) === String(friendId))
  if (idx <= 0) return list
  return [list[idx], ...list.slice(0, idx), ...list.slice(idx + 1)]
}
