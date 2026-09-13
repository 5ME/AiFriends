// 本文件只读 main.css 做源码级断言，**不得声明 jsdom 环境**。
//
// 根因（实测钉死）：jsdom 生效时，`new URL(相对路径, import.meta.url)`
// 会解析到 **jsdom 的文档基准**而不是文件路径：
//   不带环境声明 → [protocol] file:  → fileURLToPath OK
//   带环境声明   → [protocol] http:  → href = http://localhost:3000/src/assets/main.css
//                                     → fileURLToPath 抛 "The URL must be of scheme file"
//
// ⚠️ `import.meta.url` **本身始终是 file://**（实测），失败点在**相对解析**那一步。
// 触发条件是"**该文件自身**是否声明 jsdom"，与"同一次 run 里有几个 jsdom 文件"无关：
//   对照实验（同一次 run 跑 3 个 jsdom 文件 + 2 个读文件测试）
//     不带声明的读文件测试 → protocol file: → OK
//     带声明的读文件测试   → protocol http: → THROW
// 两者唯一差异是文件自身的环境声明，故可排除"多 jsdom 文件并发"这一假设。
//
// 若将来确需"jsdom + 读文件"同时成立，用 path.join(process.cwd(), 'src/assets/main.css')
// （jsdom 下实测可读到内容）。**不要**用 `?raw` 导入——Tailwind 处理下取到空串（实测 0 字节）。
//
// ⚠️ 另：连注释里也不能出现那个环境声明字符串——Vitest 按**全文字面量**匹配 pragma，
// 本文件第一版把它写在注释里（"不加 XXX"），结果仍被切到 jsdom。
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const css = readFileSync(
  fileURLToPath(new URL('../../assets/main.css', import.meta.url)),
  'utf8',
)

describe('思考中三点（4A T4：替换 CSS 停不掉的 daisyUI SMIL）', () => {
  it('.thinking-dot 用 currentColor 取色（4B 浅色模式复用前提）', () => {
    const block = css.match(/\.thinking-dot\s*\{[^}]*\}/s)?.[0] ?? ''
    expect(block).toContain('currentColor')
  })

  it('定义了 thinking-bounce 关键帧', () => {
    expect(css).toContain('@keyframes thinking-bounce')
  })

  it('reduced-motion 下三点静止但保留可见（opacity 不得为 0）', () => {
    const reduce = css.match(/@media \(prefers-reduced-motion: reduce\)\s*\{[\s\S]*?\n\}/)?.[0] ?? ''
    expect(reduce).toContain('.thinking-dot')
    expect(reduce).toMatch(/animation:\s*none/)
    expect(reduce).not.toMatch(/\.thinking-dot[^}]*opacity:\s*0[;\s]/)
  })

  it('同一 reduce 块内覆盖骨架 shimmer（4A F7 遗漏项）', () => {
    const reduce = css.match(/@media \(prefers-reduced-motion: reduce\)\s*\{[\s\S]*?\n\}/)?.[0] ?? ''
    expect(reduce).toContain('.skeleton-shimmer')
  })
})
