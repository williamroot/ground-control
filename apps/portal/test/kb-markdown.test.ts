import { describe, expect, it } from 'vitest'
import { parseInline, parseMarkdown, sanitizeHref } from '../components/kb/markdown'

// Spec #3 · V1 — conversor mínimo de markdown → AST (sem v-html). Cobre a
// sintaxe suportada (título, parágrafo, lista, código, negrito, itálico,
// link) e os dois casos de ataque exigidos: <script> e <img onerror=>.

describe('parseMarkdown: blocos', () => {
  it('título (# .. ######) vira heading com o level correto', () => {
    const blocks = parseMarkdown('# Título principal\n\n## Subtítulo')
    expect(blocks).toEqual([
      { type: 'heading', level: 1, inline: [{ type: 'text', value: 'Título principal' }] },
      { type: 'heading', level: 2, inline: [{ type: 'text', value: 'Subtítulo' }] },
    ])
  })

  it('parágrafo simples', () => {
    const blocks = parseMarkdown('Isto é um parágrafo simples.')
    expect(blocks).toEqual([
      { type: 'paragraph', inline: [{ type: 'text', value: 'Isto é um parágrafo simples.' }] },
    ])
  })

  it('duas linhas contíguas sem linha em branco formam um único parágrafo', () => {
    const blocks = parseMarkdown('linha um\nlinha dois')
    expect(blocks).toHaveLength(1)
    expect(blocks[0].type).toBe('paragraph')
  })

  it('lista não-ordenada (- ou *)', () => {
    const blocks = parseMarkdown('- item um\n- item dois')
    expect(blocks).toEqual([
      {
        type: 'list',
        ordered: false,
        items: [
          [{ type: 'text', value: 'item um' }],
          [{ type: 'text', value: 'item dois' }],
        ],
      },
    ])
  })

  it('lista ordenada (1. 2. ...)', () => {
    const blocks = parseMarkdown('1. primeiro\n2. segundo')
    expect(blocks).toEqual([
      {
        type: 'list',
        ordered: true,
        items: [
          [{ type: 'text', value: 'primeiro' }],
          [{ type: 'text', value: 'segundo' }],
        ],
      },
    ])
  })

  it('bloco de código (```) preserva o conteúdo cru, sem parse inline', () => {
    const blocks = parseMarkdown('```\nconst x = 1\n**não vira negrito**\n```')
    expect(blocks).toEqual([
      { type: 'code', value: 'const x = 1\n**não vira negrito**' },
    ])
  })

  it('múltiplos blocos em sequência', () => {
    const blocks = parseMarkdown('# Guia\n\nPasso a passo:\n\n- um\n- dois')
    expect(blocks.map(b => b.type)).toEqual(['heading', 'paragraph', 'list'])
  })

  it('markdown vazio → sem blocos', () => {
    expect(parseMarkdown('')).toEqual([])
    expect(parseMarkdown('   \n  \n')).toEqual([])
  })
})

describe('parseInline: negrito, itálico, código, link', () => {
  it('negrito **...**', () => {
    expect(parseInline('um **texto em negrito** aqui')).toEqual([
      { type: 'text', value: 'um ' },
      { type: 'bold', value: 'texto em negrito' },
      { type: 'text', value: ' aqui' },
    ])
  })

  it('itálico *...* e _..._', () => {
    expect(parseInline('*itálico*')).toEqual([{ type: 'italic', value: 'itálico' }])
    expect(parseInline('_itálico_')).toEqual([{ type: 'italic', value: 'itálico' }])
  })

  it('código inline `...`', () => {
    expect(parseInline('use `npm install`')).toEqual([
      { type: 'text', value: 'use ' },
      { type: 'code', value: 'npm install' },
    ])
  })

  it('link [texto](url) com esquema seguro', () => {
    expect(parseInline('[ajuda](https://exemplo.com/ajuda)')).toEqual([
      { type: 'link', href: 'https://exemplo.com/ajuda', value: 'ajuda' },
    ])
  })

  it('link relativo (/rota) é aceito', () => {
    expect(parseInline('[chamados](/tickets)')).toEqual([
      { type: 'link', href: '/tickets', value: 'chamados' },
    ])
  })

  it('marcadores sem par de fechamento viram texto literal', () => {
    expect(parseInline('preço: R$ 10 * 2 = R$ 20')).toEqual([
      { type: 'text', value: 'preço: R$ 10 * 2 = R$ 20' },
    ])
  })
})

describe('sanitizeHref: allowlist de esquema (defesa contra link malicioso)', () => {
  it('http/https/mailto são aceitos', () => {
    expect(sanitizeHref('https://exemplo.com')).toBe('https://exemplo.com')
    expect(sanitizeHref('http://exemplo.com')).toBe('http://exemplo.com')
    expect(sanitizeHref('mailto:suporte@exemplo.com')).toBe('mailto:suporte@exemplo.com')
  })
  it('relativo (/ ou #) é aceito', () => {
    expect(sanitizeHref('/catalogo')).toBe('/catalogo')
    expect(sanitizeHref('#secao')).toBe('#secao')
  })
  it('javascript: é rejeitado (null)', () => {
    expect(sanitizeHref('javascript:alert(1)')).toBeNull()
  })
  it('data: é rejeitado (null)', () => {
    expect(sanitizeHref('data:text/html,<script>alert(1)</script>')).toBeNull()
  })
  it('vazio é rejeitado', () => {
    expect(sanitizeHref('')).toBeNull()
    expect(sanitizeHref('   ')).toBeNull()
  })
  it('link com href rejeitado ainda carrega o texto (renderiza como span, não <a>)', () => {
    const nodes = parseInline('[clique aqui](javascript:alert(1))')
    expect(nodes).toEqual([{ type: 'link', href: null, value: 'clique aqui' }])
  })
})

describe('defesa XSS: <script> e <img onerror=> nunca viram marcação', () => {
  it('<script>alert(1)</script> literal no corpo cai inteiro num nó de texto', () => {
    const blocks = parseMarkdown('Aviso: <script>alert(1)</script> não é executado.')
    expect(blocks).toHaveLength(1)
    expect(blocks[0]).toEqual({
      type: 'paragraph',
      inline: [{ type: 'text', value: 'Aviso: <script>alert(1)</script> não é executado.' }],
    })
    // Nenhum outro tipo de nó (heading/bold/link/code) foi produzido a partir do tag.
    const flat = JSON.stringify(blocks)
    expect(flat).not.toContain('"type":"link"')
  })

  it('<img onerror=alert(1) src=x> literal também cai como texto puro', () => {
    const blocks = parseMarkdown('<img onerror=alert(1) src=x>')
    expect(blocks).toEqual([
      { type: 'paragraph', inline: [{ type: 'text', value: '<img onerror=alert(1) src=x>' }] },
    ])
  })

  it('<script> dentro de um item de lista continua como texto no item', () => {
    const blocks = parseMarkdown('- <script>alert(1)</script>')
    expect(blocks).toEqual([
      { type: 'list', ordered: false, items: [[{ type: 'text', value: '<script>alert(1)</script>' }]] },
    ])
  })

  it('link com javascript: disfarçado de markdown não produz href executável', () => {
    const blocks = parseMarkdown('[abrir](javascript:alert(document.cookie))')
    expect(blocks).toEqual([
      { type: 'paragraph', inline: [{ type: 'link', href: null, value: 'abrir' }] },
    ])
  })
})
