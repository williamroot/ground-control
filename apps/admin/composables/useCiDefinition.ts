// Classes de CI do Znuny (Spec #4, Bloco B) — lógica PURA do editor de
// definição. Sem Nuxt/DOM: testável isoladamente (vitest).
//
// Contrato consumido (sidecar `routers/admin_znuny.py`):
//   GET /api/admin/znuny/ci-classes                    -> { items: CiClassRow[] }
//   GET /api/admin/znuny/ci-classes/{id}/definition     -> CiClassDefinition
//   PUT /api/admin/znuny/ci-classes/{id}/definition     body: { Definition: string }
// `DefinitionCheck` roda no Znuny ANTES de gravar — reprovar vira 422 com a
// mensagem do Znuny em `detail` (nunca gravamos localmente antes disso: a
// verdade é sempre o retorno do sidecar). Uma definição gravada com sucesso
// SEMPRE cria uma nova versão no Znuny — não existe overwrite.

export interface CiClassRow {
  ClassID: string | number
  Name: string
  ValidID: string | number
  Comment?: string | null
}

export interface CiClassDefinition {
  ClassID: string | number
  Definition: string
  DefinitionID?: string | number | null
  Version?: number | null
  CreateTime?: string | null
  CreateBy?: string | null
}

// Znuny: 1 válido, 2 inválido, 3 inválido temporariamente. Qualquer outro
// valor é tratado como desconhecido (não trava a UI).
export function ciValidLabel(validId: string | number | null | undefined): string {
  switch (String(validId ?? '')) {
    case '1': return 'válido'
    case '2': return 'inválido'
    case '3': return 'inválido temporariamente'
    default: return 'desconhecido'
  }
}

export type SemanticColor = 'success' | 'error' | 'warning' | 'neutral'

export function ciValidColor(validId: string | number | null | undefined): SemanticColor {
  switch (String(validId ?? '')) {
    case '1': return 'success'
    case '2': return 'error'
    case '3': return 'warning'
    default: return 'neutral'
  }
}

/** Rascunho difere do carregado do Znuny (guia se o botão Salvar liga). */
export function isDefinitionDirty(original: string, draft: string): boolean {
  return original.trim() !== draft.trim()
}

/** Guarda mínima client-side (UX) — a verdade é o `DefinitionCheck` do Znuny via 422. */
export function isDefinitionSaveable(draft: string): boolean {
  return draft.trim().length > 0
}

export function buildDefinitionPayload(draft: string): { Definition: string } {
  return { Definition: draft }
}

interface SidecarErrorLike {
  statusCode?: number
  data?: { detail?: string }
}

/**
 * Extrai a mensagem de erro de um 422 do sidecar (a mensagem real do
 * `DefinitionCheck` do Znuny). Sem essa mensagem o operador não tem como
 * saber o que corrigir na definição — nunca mostrar um erro genérico quando
 * o sidecar mandou detalhe.
 */
export function extractDefinitionError(err: unknown): string {
  const e = err as SidecarErrorLike
  const detail = e?.data?.detail
  if (detail && detail.trim()) return detail
  if (e?.statusCode === 422) return 'O Znuny recusou a definição, mas não informou o motivo.'
  return 'Falha ao salvar a definição. Tente novamente.'
}
