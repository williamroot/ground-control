// Conversor mínimo de markdown → AST (Spec #3 · V1, base de conhecimento).
//
// NUNCA usamos `v-html`: o corpo de um artigo vem do cliente/da IA e é
// não-confiável (regra global). Em vez de montar uma string HTML e injetá-la,
// este módulo produz uma árvore tipada de nós (`BlockNode`/`InlineNode`) que o
// componente `MarkdownBody.vue` percorre com `v-for`/`<template>` normais —
// todo texto passa pela interpolação `{{ }}` do Vue, que escapa por padrão.
// Um `<script>` ou `<img onerror=...>` literal no markdown nunca vira tag: o
// parser só reconhece a sintaxe markdown abaixo (`#`, `-`/`1.`, `**`, `*`/`_`,
// `` ` ``, `[]()`,  ```` ``` ````); qualquer outro caractere — incluindo `<`/`>`
// — é tratado como texto puro e cai num nó `text`, nunca é interpretado como
// marcação. `sanitizeHref` ainda faz o allowlist de esquema do link (não dá
// pra confiar na interpolação de texto para atributos como `href`).
//
// Suporte: título (#..######), parágrafo, lista (ordenada/não-ordenada),
// bloco de código (```), negrito (**), itálico (*/_), código inline (`), link.

export interface TextNode { type: 'text', value: string }
export interface BoldNode { type: 'bold', value: string }
export interface ItalicNode { type: 'italic', value: string }
export interface InlineCodeNode { type: 'code', value: string }
export interface LinkNode { type: 'link', href: string | null, value: string }
export type InlineNode = TextNode | BoldNode | ItalicNode | InlineCodeNode | LinkNode

export interface HeadingBlock { type: 'heading', level: number, inline: InlineNode[] }
export interface ParagraphBlock { type: 'paragraph', inline: InlineNode[] }
export interface ListBlock { type: 'list', ordered: boolean, items: InlineNode[][] }
export interface CodeBlock { type: 'code', value: string }
export type BlockNode = HeadingBlock | ParagraphBlock | ListBlock | CodeBlock

const SAFE_SCHEMES = new Set(['http:', 'https:', 'mailto:'])

/**
 * Allowlist de esquema para `href` de link — nunca `javascript:`/`data:`/etc.
 * Relativo (`/algo`, `#ancora`) é aceito sem parse de URL absoluta.
 * Fora do allowlist → `null` (o link vira texto simples, sem `href`).
 */
export function sanitizeHref(url: string): string | null {
  const trimmed = url.trim()
  if (!trimmed) return null
  if (trimmed.startsWith('/') || trimmed.startsWith('#')) return trimmed
  try {
    const parsed = new URL(trimmed)
    return SAFE_SCHEMES.has(parsed.protocol) ? trimmed : null
  }
  catch {
    return null
  }
}

/** Tokeniza um trecho de texto em nós inline (negrito, itálico, código, link, texto). */
export function parseInline(text: string): InlineNode[] {
  const nodes: InlineNode[] = []
  let buf = ''
  let i = 0
  const flush = () => {
    if (buf) {
      nodes.push({ type: 'text', value: buf })
      buf = ''
    }
  }

  while (i < text.length) {
    // código inline `...`
    if (text[i] === '`') {
      const end = text.indexOf('`', i + 1)
      if (end !== -1) {
        flush()
        nodes.push({ type: 'code', value: text.slice(i + 1, end) })
        i = end + 1
        continue
      }
    }

    // negrito **...**
    if (text.startsWith('**', i)) {
      const end = text.indexOf('**', i + 2)
      if (end !== -1 && end > i + 2) {
        flush()
        nodes.push({ type: 'bold', value: text.slice(i + 2, end) })
        i = end + 2
        continue
      }
    }

    // itálico *...* ou _..._
    if (text[i] === '*' || text[i] === '_') {
      const marker = text[i]
      const end = text.indexOf(marker, i + 1)
      if (end !== -1 && end > i + 1) {
        flush()
        nodes.push({ type: 'italic', value: text.slice(i + 1, end) })
        i = end + 1
        continue
      }
    }

    // link [texto](url) — parênteses do próprio `url` são balanceados (ex.:
    // "(https://exemplo.com/a(b))"), não paramos no primeiro ')' que achar.
    if (text[i] === '[') {
      const closeBracket = text.indexOf(']', i + 1)
      if (closeBracket !== -1 && text[closeBracket + 1] === '(') {
        let depth = 1
        let j = closeBracket + 2
        while (j < text.length && depth > 0) {
          if (text[j] === '(') depth++
          else if (text[j] === ')') { depth--; if (depth === 0) break }
          j++
        }
        if (depth === 0) {
          flush()
          const linkText = text.slice(i + 1, closeBracket)
          const url = text.slice(closeBracket + 2, j)
          nodes.push({ type: 'link', href: sanitizeHref(url), value: linkText || url })
          i = j + 1
          continue
        }
      }
    }

    buf += text[i]
    i++
  }
  flush()
  return nodes
}

const RE_HEADING = /^(#{1,6})\s+(.*)$/
const RE_UL = /^[-*]\s+(.*)$/
const RE_OL = /^\d+\.\s+(.*)$/
const RE_FENCE = /^```/

/** Markdown completo (fonte crua, não-confiável) → árvore de blocos. */
export function parseMarkdown(source: string): BlockNode[] {
  const lines = (source ?? '').replace(/\r\n/g, '\n').split('\n')
  const blocks: BlockNode[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    if (line.trim() === '') {
      i++
      continue
    }

    // bloco de código ```
    if (RE_FENCE.test(line.trim())) {
      const codeLines: string[] = []
      i++
      while (i < lines.length && !RE_FENCE.test(lines[i].trim())) {
        codeLines.push(lines[i])
        i++
      }
      i++ // pula a cerca de fechamento (ou fim do texto, se não fechado)
      blocks.push({ type: 'code', value: codeLines.join('\n') })
      continue
    }

    // título
    const heading = RE_HEADING.exec(line)
    if (heading) {
      blocks.push({ type: 'heading', level: heading[1].length, inline: parseInline(heading[2].trim()) })
      i++
      continue
    }

    // lista (não-ordenada ou ordenada) — não mistura os dois tipos num só bloco
    if (RE_UL.test(line) || RE_OL.test(line)) {
      const ordered = RE_OL.test(line)
      const items: InlineNode[][] = []
      while (i < lines.length) {
        const m = ordered ? RE_OL.exec(lines[i]) : RE_UL.exec(lines[i])
        if (!m) break
        items.push(parseInline(m[1]))
        i++
      }
      blocks.push({ type: 'list', ordered, items })
      continue
    }

    // parágrafo: acumula linhas até uma linha em branco ou o início de outro bloco
    const paraLines: string[] = []
    while (
      i < lines.length
      && lines[i].trim() !== ''
      && !RE_HEADING.test(lines[i])
      && !RE_UL.test(lines[i])
      && !RE_OL.test(lines[i])
      && !RE_FENCE.test(lines[i].trim())
    ) {
      paraLines.push(lines[i])
      i++
    }
    blocks.push({ type: 'paragraph', inline: parseInline(paraLines.join(' ')) })
  }

  return blocks
}
