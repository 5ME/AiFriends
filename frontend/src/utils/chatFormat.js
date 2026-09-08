// 聊天消息分组/日期/时间纯函数（LD §9.2 契约，Phase 2 消费 Step A created_at）

const GROUP_GAP_MINUTES = 5

/**
 * 两条消息之间的分钟差。
 * time 为空/非法时按时间差 0 处理（无 time 的历史消息恒与相邻消息同组）。
 * @param {{time?: string|null}} prev
 * @param {{time?: string|null}} cur
 * @returns {number} cur.time - prev.time（分钟）
 */
function timeDiffMinutes(prev, cur) {
  const prevTime = prev?.time
  const curTime = cur?.time
  if (!prevTime || !curTime) return 0
  const prevMs = new Date(prevTime).getTime()
  const curMs = new Date(curTime).getTime()
  if (Number.isNaN(prevMs) || Number.isNaN(curMs)) return 0
  return (curMs - prevMs) / 60000
}

/**
 * 按「同 role 连续且时间差 ≤5min」分组；首条恒为组首。
 * 无 time 的历史消息时间差按 0 处理（与相邻消息同组，行为确定性锁定）。
 * @param {Array<{role:string, time?:string|null}>} history
 * @returns {Array<{startIndex:number, endIndex:number}>} endIndex 不含（切片语义）
 */
export function groupMessages(history) {
  if (!Array.isArray(history) || history.length === 0) return []
  const groups = []
  let startIndex = 0
  for (let i = 1; i < history.length; i++) {
    const prev = history[i - 1]
    const cur = history[i]
    const roleChanged = cur.role !== prev.role
    const gapMinutes = timeDiffMinutes(prev, cur)
    if (roleChanged || gapMinutes > GROUP_GAP_MINUTES) {
      groups.push({ startIndex, endIndex: i })
      startIndex = i
    }
  }
  groups.push({ startIndex, endIndex: history.length })
  return groups
}

/** 解析时间（支持 ISO 字符串 / Date），非法返回 null */
function parseDate(value) {
  if (!value) return null
  const d = value instanceof Date ? value : new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

function isSameDay(a, b) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

/**
 * 日期分隔胶囊文案。
 * @param {string|Date|null} prev 上一条消息时间（首条传 null）
 * @param {string|Date|null} cur 当前消息时间
 * @returns {string|null} 今天/昨天/M月D日；同一天（或 cur 无时间）返回 null
 */
export function dateLabel(prev, cur) {
  const prevDate = parseDate(prev)
  const curDate = parseDate(cur)
  if (!curDate) return null
  if (prevDate && isSameDay(prevDate, curDate)) return null

  const today = new Date()
  if (isSameDay(today, curDate)) return '今天'
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  if (isSameDay(yesterday, curDate)) return '昨天'
  return `${curDate.getMonth() + 1}月${curDate.getDate()}日`
}

/**
 * HH:mm（本地时区，补零）。非法/空时间返回 ''。
 * @param {string|Date|null} iso
 * @returns {string}
 */
export function formatTime(iso) {
  const d = parseDate(iso)
  if (!d) return ''
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}
