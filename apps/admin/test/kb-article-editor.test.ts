// Spec #3 (V1) — lógica pura do formulário de Base de Conhecimento do console.
// Sem Nuxt/DOM: testa normalização de tags, validação (espelho do 422 do
// sidecar) e montagem do payload de criação/edição.
import { describe, expect, it } from 'vitest'
import {
  buildKbArticlePayload,
  emptyKbDraft,
  isKbArticleValid,
  kbDraftFromDetail,
  kbStatusColor,
  kbStatusLabel,
  kbVisibilityLabel,
  parseTagsInput,
  tagsToInput,
  validateKbArticle,
  type KbArticleDetail,
} from '../composables/useKbArticle'

describe('parseTagsInput — normalização', () => {
  it('separa por vírgula, remove espaços e vira minúsculas', () => {
    expect(parseTagsInput(' VPN , E-mail ,  Redes ')).toEqual(['vpn', 'e-mail', 'redes'])
  })

  it('descarta vazios e duplicatas (case-insensitive)', () => {
    expect(parseTagsInput('vpn,, VPN , redes,redes')).toEqual(['vpn', 'redes'])
  })

  it('limita a 10 tags', () => {
    const raw = Array.from({ length: 15 }, (_, i) => `tag${i}`).join(',')
    expect(parseTagsInput(raw)).toHaveLength(10)
  })

  it('tagsToInput reconstitui a string editável', () => {
    expect(tagsToInput(['vpn', 'redes'])).toBe('vpn, redes')
  })
})

describe('validateKbArticle — espelho do 422', () => {
  it('rejeita rascunho vazio', () => {
    const draft = { ...emptyKbDraft(), tags: [] }
    const errors = validateKbArticle(draft)
    expect(errors.length).toBeGreaterThan(0)
    expect(isKbArticleValid(draft)).toBe(false)
  })

  it('título curto demais é inválido', () => {
    const draft = { ...emptyKbDraft(), title: 'ab', body_markdown: 'conteúdo', category: 'redes', tags: [] }
    expect(validateKbArticle(draft).some(e => e.includes('Título'))).toBe(true)
  })

  it('resumo acima de 500 chars é inválido', () => {
    const draft = {
      ...emptyKbDraft(),
      title: 'Como resetar a senha',
      summary: 'x'.repeat(501),
      body_markdown: 'conteúdo',
      category: 'contas',
      tags: [],
    }
    expect(validateKbArticle(draft).some(e => e.includes('Resumo'))).toBe(true)
  })

  it('mais de 10 tags é inválido', () => {
    const draft = {
      ...emptyKbDraft(),
      title: 'Como resetar a senha',
      body_markdown: 'conteúdo',
      category: 'contas',
      tags: Array.from({ length: 11 }, (_, i) => `t${i}`),
    }
    expect(validateKbArticle(draft).some(e => e.includes('10 tags'))).toBe(true)
  })

  it('tag acima de 30 chars é inválida', () => {
    const draft = {
      ...emptyKbDraft(),
      title: 'Como resetar a senha',
      body_markdown: 'conteúdo',
      category: 'contas',
      tags: ['x'.repeat(31)],
    }
    expect(validateKbArticle(draft).some(e => e.includes('excede 30'))).toBe(true)
  })

  it('visibilidade/status fora do enum são inválidos', () => {
    const draft = {
      ...emptyKbDraft(),
      title: 'Como resetar a senha',
      body_markdown: 'conteúdo',
      category: 'contas',
      tags: [],
      visibility: 'weird' as never,
      status: 'weird' as never,
    }
    const errors = validateKbArticle(draft)
    expect(errors.some(e => e.includes('Visibilidade'))).toBe(true)
    expect(errors.some(e => e.includes('Status'))).toBe(true)
  })

  it('aceita um rascunho válido', () => {
    const draft = {
      ...emptyKbDraft(),
      title: 'Como resetar a senha do e-mail',
      summary: 'Passo a passo rápido.',
      body_markdown: '## Passos\n1. Acesse o portal\n2. Clique em redefinir',
      category: 'contas',
      tags: ['e-mail', 'senha'],
      visibility: 'public' as const,
      status: 'published' as const,
    }
    expect(isKbArticleValid(draft)).toBe(true)
  })
})

describe('buildKbArticlePayload', () => {
  it('normaliza espaços e omite resumo vazio', () => {
    const draft = {
      ...emptyKbDraft(),
      title: '  Como resetar a senha  ',
      summary: '   ',
      body_markdown: '  conteúdo  ',
      category: '  contas  ',
      tags: ['senha'],
    }
    const payload = buildKbArticlePayload(draft)
    expect(payload.title).toBe('Como resetar a senha')
    expect(payload.summary).toBeUndefined()
    expect(payload.body_markdown).toBe('conteúdo')
    expect(payload.category).toBe('contas')
    expect(payload.tags).toEqual(['senha'])
  })
})

describe('kbDraftFromDetail', () => {
  it('preenche o rascunho a partir do artigo carregado', () => {
    const article: KbArticleDetail = {
      id: '1',
      slug: 'como-resetar-a-senha',
      title: 'Como resetar a senha',
      summary: 'Resumo',
      body_markdown: 'conteúdo completo',
      category: 'contas',
      tags: ['senha'],
      visibility: 'internal',
      status: 'draft',
      views: 3,
      updated_at: '2026-01-01T00:00:00Z',
      author_login: 'agente1',
      created_at: '2026-01-01T00:00:00Z',
    }
    const draft = kbDraftFromDetail(article)
    expect(draft.title).toBe('Como resetar a senha')
    expect(draft.body_markdown).toBe('conteúdo completo')
    expect(draft.status).toBe('draft')
  })
})

describe('rótulos e cores', () => {
  it('traduz visibilidade e status', () => {
    expect(kbVisibilityLabel('public')).toBe('Público')
    expect(kbVisibilityLabel('internal')).toBe('Interno')
    expect(kbStatusLabel('published')).toBe('Publicado')
  })

  it('cor de status segue o estado (H8, sem cor de marca)', () => {
    expect(kbStatusColor('published')).toBe('success')
    expect(kbStatusColor('draft')).toBe('warning')
    expect(kbStatusColor('archived')).toBe('neutral')
  })
})
