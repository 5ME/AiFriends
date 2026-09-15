import { beforeEach, describe, expect, it } from 'vitest'
import { __resetSessionPreview, promote, setPreview, useSessionPreview } from '../useSessionPreview.js'

describe('useSessionPreview（会话栏预览乐观更新，M 档）', () => {
  beforeEach(() => {
    __resetSessionPreview()   // 模块状态跨用例存活，必须重置
  })

  it('初始无预览、无最近更新', () => {
    const { previews, latestId } = useSessionPreview()
    expect(Object.keys(previews)).toEqual([])
    expect(latestId.value).toBeNull()
  })

  it('setPreview 写入文本与时间，并把该 id 记为最近更新（键统一为字符串）', () => {
    const { previews, latestId, setPreview } = useSessionPreview()
    setPreview(3, { text: '你好', at: '2026-03-15T09:05:00+08:00' })

    expect(previews[3]).toEqual({ text: '你好', at: '2026-03-15T09:05:00+08:00' })
    expect(previews['3']).toEqual({ text: '你好', at: '2026-03-15T09:05:00+08:00' })
    expect(latestId.value).toBe('3')
  })

  it('at 缺省 → 当前时间 ISO 串', () => {
    const { previews, setPreview } = useSessionPreview()
    const before = Date.now()
    setPreview(3, { text: '你好' })

    const at = new Date(previews[3].at).getTime()
    expect(Number.isNaN(at)).toBe(false)
    expect(at).toBeGreaterThanOrEqual(before - 1000)
    expect(at).toBeLessThanOrEqual(Date.now() + 1000)
  })

  it('写入前归一化 + 截断 60 —— 与服务端 get_list 同一规则（F7-1）', () => {
    const { previews, setPreview } = useSessionPreview()
    setPreview(3, { text: '第一行\n\n第二行   ' + 'a'.repeat(100) })

    expect(previews[3].text).toBe('第一行 第二行 ' + 'a'.repeat(52))
    expect(previews[3].text).toHaveLength(60)
    expect(previews[3].text).not.toContain('\n')
  })

  it('超长用户消息不会把可访问名称撑大（预览是按钮名称的一部分）', () => {
    const { previews, setPreview } = useSessionPreview()
    setPreview(3, { text: '啊'.repeat(800) })

    expect(previews[3].text).toHaveLength(60)
  })

  it('全空白文本 → 空串（调用方的"空则不覆盖"规则因此仍然有效）', () => {
    const { previews, setPreview } = useSessionPreview()
    setPreview(3, { text: '  \n\t  ' })

    expect(previews[3].text).toBe('')
  })

  it('同一 id 再次写入 → 覆盖（发送时写用户文本，流结束时改写 AI 文本）', () => {
    const { previews, setPreview } = useSessionPreview()
    setPreview(3, { text: '我说的话', at: '2026-03-15T09:05:00+08:00' })
    setPreview(3, { text: 'AI 的回复', at: '2026-03-15T09:06:00+08:00' })

    expect(previews[3]).toEqual({ text: 'AI 的回复', at: '2026-03-15T09:06:00+08:00' })
    expect(Object.keys(previews)).toHaveLength(1)
  })

  it('不同 id → latestId 跟随最后一次（会话栏据此置顶）', () => {
    const { latestId, setPreview } = useSessionPreview()
    setPreview(3, { text: 'a' })
    setPreview(7, { text: 'b' })
    setPreview(3, { text: 'c' })

    expect(latestId.value).toBe('3')
  })

  it('模块级单例：两处调用读到同一状态（会话栏与聊天窗是兄弟子树）', () => {
    const a = useSessionPreview()
    const b = useSessionPreview()
    a.setPreview(3, { text: '跨子树共享', at: '2026-03-15T09:05:00+08:00' })

    expect(b.previews[3].text).toBe('跨子树共享')
  })

  it('__resetSessionPreview 清空状态', () => {
    const { previews, latestId, setPreview } = useSessionPreview()
    setPreview(3, { text: 'a' })
    __resetSessionPreview()

    expect(Object.keys(previews)).toEqual([])
    expect(latestId.value).toBeNull()
  })
})

describe('promote（会话栏置顶，M 档；放本模块是为了与 previews 的键规则同源）', () => {
  const list = () => [{ id: 3 }, { id: 7 }, { id: 12 }]

  it('命中中间项 → 该项到首位，其余保持相对顺序', () => {
    expect(promote(list(), '7').map((s) => s.id)).toEqual([7, 3, 12])
  })

  it('已在首位 → 返回原数组引用（不触发无意义的重渲染）', () => {
    const l = list()
    expect(promote(l, '3')).toBe(l)
  })

  it('未命中 → 返回原数组引用', () => {
    const l = list()
    expect(promote(l, '99')).toBe(l)
  })

  it('id 类型混用（接口给 number / 键是 string）→ 仍能命中', () => {
    expect(promote(list(), 12).map((s) => s.id)).toEqual([12, 3, 7])
  })

  it('空列表 → 原样返回', () => {
    const l = []
    expect(promote(l, '3')).toBe(l)
  })
})
