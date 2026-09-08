// @vitest-environment jsdom
// XSS 用例：DOMPurify 需要 DOM 环境（按需启用，见 Q5 拍板）
import { describe, expect, it } from 'vitest'
import { renderMarkdown } from '../markdown'

describe('renderMarkdown（XSS 白名单管线）', () => {
  it('剥离 <script>（含内容）', () => {
    const out = renderMarkdown('<script>alert(1)</script>你好')
    expect(out).not.toContain('<script')
    expect(out).not.toContain('alert(1)')
    expect(out).toContain('你好')
  })

  it('剥离 <img onerror>（禁 img）', () => {
    const out = renderMarkdown('图：<img src=x onerror="alert(2)">')
    expect(out).not.toContain('<img')
    expect(out).not.toContain('onerror')
  })

  it('剥离内联事件属性（on*）', () => {
    const out = renderMarkdown('<p onclick="alert(3)">点我</p>')
    expect(out).not.toContain('onclick')
    expect(out).toContain('点我')
  })

  it('剥离 javascript: 协议链接', () => {
    const out = renderMarkdown('[点我](javascript:alert(4))')
    expect(out).not.toContain('javascript:')
  })

  it('保留白名单标签：加粗/斜体/行内代码', () => {
    const out = renderMarkdown('**加粗** *斜体* `code`')
    expect(out).toContain('<strong>加粗</strong>')
    expect(out).toContain('<em>斜体</em>')
    expect(out).toContain('<code>code</code>')
  })

  it('保留列表/代码块/引用/标题', () => {
    const out = renderMarkdown('# 标题\n\n- a\n- b\n\n> 引用\n\n```js\nconst x = 1\n```')
    expect(out).toContain('<h1>标题</h1>')
    expect(out).toContain('<ul>')
    expect(out).toContain('<li>a</li>')
    expect(out).toContain('<blockquote>')
    expect(out).toContain('<pre>')
    expect(out).toContain('const x = 1')
  })

  it('安全 http 链接保留 href', () => {
    const out = renderMarkdown('[官网](https://example.com)')
    expect(out).toContain('<a')
    expect(out).toContain('href="https://example.com"')
  })

  it('空输入 → 空串', () => {
    expect(renderMarkdown('')).toBe('')
    expect(renderMarkdown(null)).toBe('')
    expect(renderMarkdown(undefined)).toBe('')
  })
})
