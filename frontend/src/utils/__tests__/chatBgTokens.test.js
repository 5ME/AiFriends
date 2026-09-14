import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
// 注：本文件同时从 main.css 与 ChatIndex.vue 读源码做断言

const css = readFileSync(fileURLToPath(new URL('../../assets/main.css', import.meta.url)), 'utf8')
// 取 .chat-window 基础块：命中第一个 "{" 到第一个 "}" —— 该块内无颜色函数嵌套，安全
const plain = css.match(/\.chat-window\s*\{[^}]*\}/)?.[0] ?? ''
// 取浅色覆盖块：用非贪婪 + s 标志，避免被下一段 "{" 提前截断
const simple = css.match(/\.chat-window\.chat-simple\s*\{[\s\S]*?\n\}/)?.[0] ?? ''

describe('4B token 家族（设计 §3.4）', () => {
  it('沉浸默认值必须与改造前逐字一致（D4B-5 零回归的前提）', () => {
    expect(plain).toContain('rgba(0, 0, 0, 0.35)')      // --cbg-bubble-ai
    expect(plain).toContain('rgba(255, 255, 255, 0.70)') // --cbg-text-2
    expect(plain).toContain('0 24px 64px rgba(0, 0, 0, 0.45)')  // --cbg-shadow
  })

  it('浅色覆盖块含设计 §3.3 的全部关键值', () => {
    expect(simple).toContain('#fafaf9')
    expect(simple).toContain('#f0efee')   // AI 气泡底（暖灰浮层，与窗口拉明度差）
    expect(simple).toContain('#e7e5e4')
    expect(simple).toContain('#1c1917')
    expect(simple).toContain('#57534e')
    expect(simple).toContain('#78716c')
    expect(simple).toContain('#f5f5f4')   // chip 底；其上的 --cbg-text-2 对比 6.99:1
  })

  it('AI 气泡两模式都不描边（硬边是"卡片感"来源；靠自身底色分层）', () => {
    // 断言"不存在描边声明"，而不是"描边值为 transparent"——后者会让无用的 token 留在表里
    expect(css).not.toMatch(/--cbg-bubble-ai-border\s*:/)
    const ai = css.match(/\.msg-bubble-ai\s*\{[^}]*\}/s)?.[0] ?? ''
    expect(ai).not.toMatch(/border:\s*1px/)
  })

  it('气泡盒模型 = master 原值（描边补偿已随取消描边回退）', () => {
    const bubble = css.match(/\.msg-bubble\s*\{[^}]*\}/s)?.[0] ?? ''
    expect(bubble).toContain('padding: 8px 12px')
    expect(bubble).not.toContain('border: 1px solid transparent')
  })

  it('舞台浅色块存在且使用 #e7e5e4（舞台略深于窗口）', () => {
    const stage = css.match(/\.chat-stage-root\.stage-simple[\s\S]*?\n\}/)?.[0] ?? ''
    expect(stage).toContain('#e7e5e4')
  })

  it('四个保真 token 的沉浸值 = 现状字面量（R6-3：把"保真"变机检）', () => {
    // 这四处的全部意义就是"等于改造前的字面量"，故逐字锁定；
    // 一个 0.05 写成 0.5 的笔误也会被拦住。
    expect(plain).toContain('rgba(0, 0, 0, 0.50)')          // --cbg-glass-btn（原 bg-black/50）
    expect(plain).toContain('rgba(0, 0, 0, 0.60)')          // --cbg-glass-btn-hover（原 bg-black/60）
    expect(plain).toContain('rgba(23, 23, 23, 0.95)')       // --cbg-modal-bg（原 bg-neutral-900/95）
    expect(plain).toContain('rgba(255, 255, 255, 0.10)')    // --cbg-modal-border（原 border-white/10）
  })

  it('用户气泡引用 var(--accent) 而非硬编码 #10b981（D4B-7）', () => {
    const bubble = css.match(/\.msg-bubble-user\s*\{[^}]*\}/)?.[0] ?? ''
    expect(bubble).toContain('var(--accent)')
    expect(bubble).not.toContain('#10b981')
  })

  it('未引入被砍掉的机制（防蔓延）', () => {
    // 只查**声明位**：main.css 的注释里本就提到过 --overlay-k / --user-bubble-bg
    // （Phase 1 留下的前瞻注释），用 not.toContain 会误报——评审实测发现
    expect(css).not.toMatch(/--overlay-k\s*:/)
    expect(css).not.toMatch(/--user-bubble-bg\s*:/)
    expect(css).not.toMatch(/--msg-text-shadow\s*:/)
  })

  it('新增的 token 与语义类不得落进 @layer（否则被 utilities 压过，浅色静默失效）', () => {
    const layers = css.match(/@layer[^{;]*/g) ?? []
    // 本批此前 main.css 零 @layer；若新增，必须显式评审（见设计 §3.4 硬性约束一）
    expect(layers).toEqual([])
  })
})
