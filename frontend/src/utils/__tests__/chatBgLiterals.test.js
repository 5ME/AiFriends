// 门禁：聊天窗口相关文件里不得残留未 token 化的颜色字面量（评审 R-4 的机制性修复）。
// 随本任务的 token 化落地——**只有 Task 5 全部改完才可能绿**（评审 R3-1 的放置要求）。
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// 前 6 个在 components/character/chat_field/ 下，后 2 个在 components/chat/chat_window/ 下
const TARGETS = [
  'chat_history/message/Message.vue',
  'chat_history/ChatHistory.vue',
  'input_field/InputField.vue',
  'input_field/Microphone.vue',
  'character_photo_field/CharacterPhotoField.vue',
  'VoiceToggle.vue',
]

// 引用浮层（评审 N1 末条：那 6 处字面量原本无任何机检）
const WINDOW_TARGETS = [
  'ChatWindow.vue',
  'WindowHeader.vue',
]

/** 扫描前剥掉全部注释：HTML <!-- -->、CSS 块注释、整行 //（评审 R3-3：
 *  Microphone.vue:261-262 的 HTML 注释续行含 bg-black/35，不剥会让门禁永远红） */
function stripComments(src) {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter((l) => !l.trim().startsWith('//'))
    .join('\n')
}

/** ① 工具类：**只认调色板名**。这样天然排除 `text-sm`(字号) / `text-center`(对齐) /
 *  `border-radius`(CSS 属性名) / `outline-none` —— 初版写成 `[a-z][a-z0-9-]*` 通配，
 *  实测把这三类全判红，门禁永远绿不了（评审 N1）。 */
const COLOR_UTIL =
  /\b(?:text|bg|border|ring|divide|outline|fill|stroke|from|to|via)-(?:white|black|neutral|stone|gray|slate|zinc|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)(?:-\d{2,3})?(?:\/\d+)?\b/g

/** ② 任意值：只认**看起来是颜色**的，并放行 var(--cbg-*)。
 *  初版的负向前瞻只挡住第一支，导致计划**要求新加**的
 *  `placeholder:text-[var(--cbg-text-3)]` 反被判红（评审 N1 实测）。 */
const ARBITRARY_COLOR =
  /\b(?:text|bg|border|ring)-\[(?!var\(--cbg-)(?:#|rgba?\(|hsla?\(|oklch\(|color-mix\()[^\]]*\]/g

const CSS_COLOR = /rgba?\(|#[0-9a-fA-F]{3,8}\b/g

/** 白名单（每条都要有依据）：
 *  - `text-white`：己方气泡绿底白字，沉浸/简约两模式都成立（设计 §3.5）
 *  - `bg-blue-400`：Microphone 六小点与音浪，品牌色保留（设计 §3.5「小点保留」） */
const ALLOWED = new Set(['text-white', 'bg-blue-400'])

/** 只扫模板部分：scoped `<style>` 里的 CSS 属性名（border-radius / text-decoration）
 *  会污染工具类扫描；样式里的颜色由 CSS_COLOR 负责（评审 N1 建议）。 */
function stripStyleBlocks(src) {
  return src.replace(/<style[\s\S]*?<\/style>/g, '')
}

function scan(raw) {
  const tmpl = stripStyleBlocks(stripComments(raw))
  const style = stripComments(raw.match(/<style[\s\S]*?<\/style>/)?.[0] ?? '')
  return [
    ...(tmpl.match(COLOR_UTIL) ?? []),
    ...(tmpl.match(ARBITRARY_COLOR) ?? []),
    ...(style.match(CSS_COLOR) ?? []),
  ].filter((h) => !ALLOWED.has(h))
}

describe('颜色字面量残留门禁（Token 化完成度）', () => {
  it('6 个聊天窗口相关文件无未 token 化残留', () => {
    const offenders = []
    for (const rel of TARGETS) {
      const raw = readFileSync(
        fileURLToPath(new URL('../../components/character/chat_field/' + rel, import.meta.url)),
        'utf8',
      )
      const hits = scan(raw)
      if (hits.length) offenders.push(rel + ': ' + [...new Set(hits)].join(', '))
    }
    for (const rel of WINDOW_TARGETS) {
      const raw = readFileSync(
        // 测试文件在 src/utils/__tests__/ → ../../ = src/，故须带 components/
        fileURLToPath(new URL('../../components/chat/chat_window/' + rel, import.meta.url)),
        'utf8',
      )
      const hits = scan(raw)
      if (hits.length) offenders.push(rel + ': ' + [...new Set(hits)].join(', '))
    }
    expect(offenders).toEqual([])
  })
})
