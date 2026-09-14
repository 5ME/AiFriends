// 移动端抽屉遮罩随模式反转（设计 §3.7，用户裁决纳入）
// 用源码断言而非组件测试：遮罩位于 lg:hidden 的 Teleport 抽屉内，
// 触发它需 mock useMediaQuery 与 Teleport 目标，成本远高于价值；
// 本条核心风险是"人删了简约分支"，源码断言足以拦住。
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

describe('抽屉遮罩（4B T6）', () => {
  it('遮罩类名随模式切换', () => {
    const src = readFileSync(
      fileURLToPath(new URL('../../views/chat/ChatIndex.vue', import.meta.url)),
      'utf8',
    )
    expect(src).toContain('bg-[#1c1917]/40')   // 简约：暖深色 40%
    expect(src).toContain('bg-black/50')       // 沉浸：现状不变
  })
})
