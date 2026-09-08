// markdown 渲染管线：marked.parse → DOMPurify 白名单（LD §9.2 / spec §5.3）
// 抽出纯函数供 Message.vue 与单测共用（XSS 用例 @vitest-environment jsdom）
import DOMPurify from 'dompurify'
import { marked } from 'marked'

/** 白名单：strong/em/ul/ol/li/code/pre/blockquote/a/br/h1~h4/p，禁 img/script 等 */
export const MARKDOWN_ALLOWED_TAGS = [
  'strong', 'em', 'ul', 'ol', 'li', 'code', 'pre', 'blockquote',
  'a', 'br', 'h1', 'h2', 'h3', 'h4', 'p',
]

/**
 * @param {string} raw 原始 markdown/文本
 * @returns {string} 白名单过滤后的 HTML（空输入返回空串）
 */
export function renderMarkdown(raw) {
  if (!raw) return ''
  const html = marked.parse(raw, { gfm: true, breaks: true })
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: MARKDOWN_ALLOWED_TAGS,
    // a 标签只放行安全协议 href（DOMPurify 默认过滤 javascript: 等）
    ALLOWED_ATTR: ['href', 'title', 'target', 'rel'],
  })
}
