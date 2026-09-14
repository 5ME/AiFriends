import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { dateLabel, formatTime, groupMessages, sessionTimeLabel } from '../chatFormat'

/** 本地时区构造 Date，避免 ISO/UTC 时差陷阱 */
function at(dayOffset, hour, minute) {
  const d = new Date()
  d.setDate(d.getDate() + dayOffset)
  d.setHours(hour, minute, 0, 0)
  return d
}

const iso = (d) => d.toISOString()

describe('groupMessages（LD §9.2）', () => {
  it('空数组 → []', () => {
    expect(groupMessages([])).toEqual([])
  })

  it('单条消息 → 一组，首条恒为组首', () => {
    const groups = groupMessages([{ role: 'ai', time: iso(at(0, 10, 0)) }])
    expect(groups).toEqual([{ startIndex: 0, endIndex: 1 }])
  })

  it('同 role 连续 → 一组', () => {
    const groups = groupMessages([
      { role: 'ai', time: iso(at(0, 10, 0)) },
      { role: 'ai', time: iso(at(0, 10, 2)) },
      { role: 'ai', time: iso(at(0, 10, 4)) },
    ])
    expect(groups).toEqual([{ startIndex: 0, endIndex: 3 }])
  })

  it('role 变化 → 新组（首条恒为组首）', () => {
    const groups = groupMessages([
      { role: 'user', time: iso(at(0, 10, 0)) },
      { role: 'ai', time: iso(at(0, 10, 1)) },
      { role: 'user', time: iso(at(0, 10, 2)) },
    ])
    expect(groups).toEqual([
      { startIndex: 0, endIndex: 1 },
      { startIndex: 1, endIndex: 2 },
      { startIndex: 2, endIndex: 3 },
    ])
  })

  it('同 role 但时间差 >5min → 新组', () => {
    const groups = groupMessages([
      { role: 'ai', time: iso(at(0, 10, 0)) },
      { role: 'ai', time: iso(at(0, 10, 5)) },
      { role: 'ai', time: iso(at(0, 10, 11)) },  // 与上一条差 6min > 5min
    ])
    expect(groups).toEqual([
      { startIndex: 0, endIndex: 2 },
      { startIndex: 2, endIndex: 3 },
    ])
  })

  it('时间差恰好 5min → 同组（边界 ≤5min）', () => {
    const groups = groupMessages([
      { role: 'ai', time: iso(at(0, 10, 0)) },
      { role: 'ai', time: iso(at(0, 10, 5)) },
    ])
    expect(groups).toEqual([{ startIndex: 0, endIndex: 2 }])
  })

  it('无 time 的历史消息按时间差 0 → 同组', () => {
    const groups = groupMessages([
      { role: 'ai', time: null },
      { role: 'ai', time: null },
      { role: 'ai' },
    ])
    expect(groups).toEqual([{ startIndex: 0, endIndex: 3 }])
  })

  it('混合场景：一条无 time 不与有 time 的相邻消息因时差拆组', () => {
    // 无 time 时该对时间差按 0 → 不拆组（行为确定性锁定）
    const groups = groupMessages([
      { role: 'ai', time: iso(at(0, 10, 0)) },
      { role: 'ai', time: null },
      { role: 'user', time: iso(at(0, 10, 1)) },
    ])
    expect(groups).toEqual([
      { startIndex: 0, endIndex: 2 },
      { startIndex: 2, endIndex: 3 },
    ])
  })

  it('非法时间字符串按时间差 0 → 同组', () => {
    const groups = groupMessages([
      { role: 'ai', time: 'not-a-date' },
      { role: 'ai', time: 'also-bad' },
    ])
    expect(groups).toEqual([{ startIndex: 0, endIndex: 2 }])
  })
})

describe('dateLabel（LD §9.2）', () => {
  it('同一天 → null', () => {
    expect(dateLabel(at(0, 9, 0), at(0, 10, 30))).toBeNull()
  })

  it('首条（prev=null）→ 今天', () => {
    expect(dateLabel(null, new Date())).toBe('今天')
  })

  it('今天 → "今天"', () => {
    expect(dateLabel(at(-1, 20, 0), at(0, 9, 0))).toBe('今天')
  })

  it('昨天 → "昨天"', () => {
    expect(dateLabel(at(-2, 20, 0), at(-1, 9, 0))).toBe('昨天')
  })

  it('跨日 → "M月D日"（不补零）', () => {
    // 用相对今天的过去日期，避免与「今天/昨天」分支撞车（机器日期无关）
    const cur = at(-10, 9, 0)
    expect(dateLabel(at(-11, 20, 0), cur)).toBe(`${cur.getMonth() + 1}月${cur.getDate()}日`)
  })

  it('跨月 → "M月D日"', () => {
    const now = new Date()
    const prev = new Date(now.getFullYear(), now.getMonth() - 3, 28, 20, 0)
    const cur = new Date(now.getFullYear(), now.getMonth() - 2, 1, 9, 0)
    expect(dateLabel(prev, cur)).toBe(`${cur.getMonth() + 1}月${cur.getDate()}日`)
  })

  it('cur 无时间 → null', () => {
    expect(dateLabel(new Date(), null)).toBeNull()
    expect(dateLabel(new Date(), undefined)).toBeNull()
  })

  it('prev 无时间但 cur 有 → 按 cur 日期出标签', () => {
    expect(dateLabel(null, new Date())).toBe('今天')
  })
})

describe('formatTime（LD §9.2）', () => {
  it('ISO → HH:mm（补零）', () => {
    expect(formatTime('2026-09-07T09:05:00')).toBe('09:05')
  })

  it('下午时间', () => {
    expect(formatTime(at(0, 15, 42))).toBe('15:42')
  })

  it('空/非法 → 空串', () => {
    expect(formatTime(null)).toBe('')
    expect(formatTime(undefined)).toBe('')
    expect(formatTime('bad')).toBe('')
  })
})

describe('sessionTimeLabel（会话栏预览时间，M 档）', () => {
  // 固定"现在"为本地时间 2026-03-15 12:00：分支断言与机器日期/时区无关
  const NOW = new Date(2026, 2, 15, 12, 0, 0)

  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('今天 → HH:mm（补零）', () => {
    expect(sessionTimeLabel(new Date(2026, 2, 15, 9, 5).toISOString())).toBe('09:05')
  })

  it('昨天 → "昨天"', () => {
    expect(sessionTimeLabel(new Date(2026, 2, 14, 23, 0).toISOString())).toBe('昨天')
  })

  it('同年更早 → "M月D日"（不补零）', () => {
    expect(sessionTimeLabel(new Date(2026, 0, 20, 8, 0).toISOString())).toBe('1月20日')
  })

  it('跨年 → "YYYY年M月D日"', () => {
    expect(sessionTimeLabel(new Date(2025, 11, 31, 8, 0).toISOString())).toBe('2025年12月31日')
  })

  it('接受 Date 实例', () => {
    expect(sessionTimeLabel(new Date(2026, 2, 15, 18, 30))).toBe('18:30')
  })

  it('空/非法 → 空串（无时间则不渲染时间列）', () => {
    expect(sessionTimeLabel(null)).toBe('')
    expect(sessionTimeLabel(undefined)).toBe('')
    expect(sessionTimeLabel('bad')).toBe('')
  })
})
