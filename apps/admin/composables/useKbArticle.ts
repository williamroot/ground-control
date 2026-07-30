// Base de Conhecimento (Spec #3, V1) — lógica pura do formulário do console:
// rascunho, normalização de tags, validação (espelho leve do 422 do sidecar,
// que é a fonte de verdade) e montagem do payload. Fora dos componentes para
// testar sem montar o Nuxt (lição #1M..#1Q).

export type KbVisibility = 'public' | 'internal'
export type KbStatus = 'draft' | 'published' | 'archived'

export interface KbArticleDraft {
  title: string
  summary: string
  body_markdown: string
  category: string
  visibility: KbVisibility
  status: KbStatus
}

export interface KbArticleListItem {
  id: string
  slug: string
  title: string
  summary: string | null
  category: string
  tags: string[]
  visibility: KbVisibility
  status: KbStatus
  views: number
  updated_at: string
}

export interface KbArticleDetail extends KbArticleListItem {
  body_markdown: string
  author_login: string | null
  created_at: string
}

export const KB_VISIBILITY_OPTIONS: { label: string, value: KbVisibility }[] = [
  { label: 'Público (portal do cliente)', value: 'public' },
  { label: 'Interno (só a equipe)', value: 'internal' },
]

export const KB_STATUS_OPTIONS: { label: string, value: KbStatus }[] = [
  { label: 'Rascunho', value: 'draft' },
  { label: 'Publicado', value: 'published' },
  { label: 'Arquivado', value: 'archived' },
]

const VISIBILITY_LABEL: Record<KbVisibility, string> = {
  public: 'Público',
  internal: 'Interno',
}

const STATUS_LABEL: Record<KbStatus, string> = {
  draft: 'Rascunho',
  published: 'Publicado',
  archived: 'Arquivado',
}

export function kbVisibilityLabel(v: string): string {
  return VISIBILITY_LABEL[v as KbVisibility] ?? v
}

export function kbStatusLabel(s: string): string {
  return STATUS_LABEL[s as KbStatus] ?? s
}

export function kbStatusColor(s: string): 'success' | 'warning' | 'neutral' {
  if (s === 'published') return 'success'
  if (s === 'draft') return 'warning'
  return 'neutral'
}

export function emptyKbDraft(): KbArticleDraft {
  return {
    title: '',
    summary: '',
    body_markdown: '',
    category: '',
    visibility: 'internal',
    status: 'draft',
  }
}

export function kbDraftFromDetail(a: KbArticleDetail): KbArticleDraft {
  return {
    title: a.title,
    summary: a.summary ?? '',
    body_markdown: a.body_markdown,
    category: a.category,
    visibility: a.visibility,
    status: a.status,
  }
}

/**
 * Normaliza a entrada de tags separada por vírgula: minúsculas, sem espaços
 * nas pontas, sem vazias, sem duplicatas, máx. 10 itens (excedente descartado).
 * Cada tag além de 30 chars é truncada em 30 (validateKbArticle ainda acusa
 * se preferir bloquear em vez de truncar — aqui só normaliza para exibição).
 */
export function parseTagsInput(raw: string): string[] {
  const seen = new Set<string>()
  const tags: string[] = []
  for (const part of raw.split(',')) {
    const tag = part.trim().toLowerCase()
    if (!tag) continue
    if (seen.has(tag)) continue
    seen.add(tag)
    tags.push(tag)
    if (tags.length >= 10) break
  }
  return tags
}

export function tagsToInput(tags: string[]): string {
  return tags.join(', ')
}

/** Validação leve (espelho do server). Retorna lista de erros; vazia = válido. */
export function validateKbArticle(draft: KbArticleDraft & { tags: string[] }): string[] {
  const errors: string[] = []
  const title = draft.title.trim()
  if (title.length < 3 || title.length > 200) errors.push('Título deve ter entre 3 e 200 caracteres.')
  if (draft.summary.trim().length > 500) errors.push('Resumo deve ter no máximo 500 caracteres.')
  const body = draft.body_markdown.trim()
  if (body.length < 1 || body.length > 50000) errors.push('Conteúdo deve ter entre 1 e 50.000 caracteres.')
  const category = draft.category.trim()
  if (category.length < 2 || category.length > 60) errors.push('Categoria deve ter entre 2 e 60 caracteres.')
  if (draft.tags.length > 10) errors.push('No máximo 10 tags.')
  for (const t of draft.tags) {
    if (t.length > 30) errors.push(`Tag "${t}" excede 30 caracteres.`)
  }
  if (!['public', 'internal'].includes(draft.visibility)) errors.push('Visibilidade inválida.')
  if (!['draft', 'published', 'archived'].includes(draft.status)) errors.push('Status inválido.')
  return errors
}

export function isKbArticleValid(draft: KbArticleDraft & { tags: string[] }): boolean {
  return validateKbArticle(draft).length === 0
}

export interface KbArticlePayload {
  title: string
  summary?: string
  body_markdown: string
  category: string
  tags: string[]
  visibility: KbVisibility
  status: KbStatus
}

export function buildKbArticlePayload(draft: KbArticleDraft & { tags: string[] }): KbArticlePayload {
  const summary = draft.summary.trim()
  return {
    title: draft.title.trim(),
    summary: summary || undefined,
    body_markdown: draft.body_markdown.trim(),
    category: draft.category.trim(),
    tags: draft.tags,
    visibility: draft.visibility,
    status: draft.status,
  }
}
