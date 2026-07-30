// Classificação do Znuny (Spec #4, Bloco A) — Tipos de chamado, Estados e
// Prioridades. Lógica PURA de rascunho/validação/payload das três abas, sem
// Nuxt/DOM (testável isoladamente). Espelho leve do 422 do sidecar, que é a
// fonte de verdade.
//
// Mesma convenção de `useZnunyObject.ts` (Filas/SLA, também Bloco A): a
// página normaliza a resposta crua do sidecar com `extractItems`/
// `extractItemId`/`extractSupport`/`toOptions`/`validLabelPt` — aqui só
// entram os `*DraftFromItem(item)` (registro cru → rascunho) e as funções de
// validação/payload. "Excluir" não existe nesta spec: o Znuny invalida com
// ValidID = 2 — a ação na UI chama-se sempre "Invalidar".

function str(v: unknown, fallback = ''): string {
  return v === null || v === undefined ? fallback : String(v)
}

// --- Tipo de chamado (Type) ---------------------------------------------------

export interface TypeDraft {
  name: string
  validId: string
}

export function emptyTypeDraft(): TypeDraft {
  return { name: '', validId: '1' }
}

export function typeDraftFromItem(item: Record<string, unknown>): TypeDraft {
  return { name: str(item.Name), validId: str(item.ValidID, '1') }
}

export function validateTypeDraft(draft: TypeDraft): string[] {
  const errors: string[] = []
  if (!draft.name.trim()) errors.push('Nome é obrigatório.')
  if (!draft.validId) errors.push('Validade é obrigatória.')
  return errors
}

export interface TypePayload { Name: string, ValidID: number }

export function buildTypePayload(draft: TypeDraft): TypePayload {
  return { Name: draft.name.trim(), ValidID: Number(draft.validId) }
}

export function buildInvalidateTypePayload(draft: TypeDraft): TypePayload {
  return buildTypePayload({ ...draft, validId: '2' })
}

// --- Prioridade (Priority) — mesma forma do Tipo ------------------------------

export type PriorityDraft = TypeDraft
export const emptyPriorityDraft = emptyTypeDraft
export const priorityDraftFromItem = typeDraftFromItem
export const validatePriorityDraft = validateTypeDraft
export type PriorityPayload = TypePayload
export const buildPriorityPayload = buildTypePayload
export const buildInvalidatePriorityPayload = buildInvalidateTypePayload

// --- Estado (State) ------------------------------------------------------------

export interface StateDraft {
  name: string
  comment: string
  validId: string
  typeId: string
}

export function emptyStateDraft(): StateDraft {
  return { name: '', comment: '', validId: '1', typeId: '' }
}

export function stateDraftFromItem(item: Record<string, unknown>): StateDraft {
  return {
    name: str(item.Name),
    comment: str(item.Comment),
    validId: str(item.ValidID, '1'),
    typeId: str(item.TypeID),
  }
}

export function validateStateDraft(draft: StateDraft): string[] {
  const errors: string[] = []
  if (!draft.name.trim()) errors.push('Nome é obrigatório.')
  if (!draft.validId) errors.push('Validade é obrigatória.')
  if (!draft.typeId) errors.push('Tipo de estado é obrigatório.')
  return errors
}

export interface StatePayload { Name: string, Comment?: string, ValidID: number, TypeID: number }

export function buildStatePayload(draft: StateDraft): StatePayload {
  return {
    Name: draft.name.trim(),
    Comment: draft.comment.trim() || undefined,
    ValidID: Number(draft.validId),
    TypeID: Number(draft.typeId),
  }
}

export function buildInvalidateStatePayload(draft: StateDraft): StatePayload {
  return buildStatePayload({ ...draft, validId: '2' })
}
