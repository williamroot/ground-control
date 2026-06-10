// Lógica PURA do editor de regras de automação (#1Q, Task 6). Sem Nuxt/DOM:
// montagem e validação do payload da regra, testável isoladamente (vitest).
// A validação de allowlist é server-side (sidecar, fonte de verdade); aqui é
// um espelho leve para feedback imediato na UI (bloqueia salvar inválido).

export interface RuleCondition {
  field: string
  op: string
  value: string
}

export interface RuleAction {
  type: string
  params: Record<string, string>
}

export interface RuleDraft {
  name: string
  trigger_event: string
  conditions: RuleCondition[]
  actions: RuleAction[]
  position: number
  enabled: boolean
}

export interface AutomationMeta {
  fields: string[]
  ops: string[]
  actions: string[]
  trigger_events: string[]
}

// Parâmetro principal esperado por cada tipo de ação (alimenta o input da UI).
export const ACTION_PARAM_KEY: Record<string, string> = {
  set_priority: 'priority',
  set_queue: 'queue',
  set_state: 'state',
  add_note: 'note',
  notify: 'message',
  ai_summarize_note: '',
}

export function emptyCondition(): RuleCondition {
  return { field: '', op: 'eq', value: '' }
}

export function emptyAction(): RuleAction {
  return { type: '', params: {} }
}

export function emptyDraft(): RuleDraft {
  return {
    name: '',
    trigger_event: '',
    conditions: [],
    actions: [],
    position: 0,
    enabled: true,
  }
}

// Monta o payload enviado ao sidecar a partir do rascunho da UI.
export function buildRulePayload(draft: RuleDraft): {
  name: string
  trigger_event: string
  conditions: { field: string, op: string, value: string }[]
  actions: { type: string, params: Record<string, string> }[]
  position: number
  enabled: boolean
} {
  return {
    name: draft.name.trim(),
    trigger_event: draft.trigger_event,
    conditions: draft.conditions.map(c => ({
      field: c.field,
      op: c.op,
      value: c.value,
    })),
    actions: draft.actions.map(a => ({ type: a.type, params: { ...a.params } })),
    position: draft.position,
    enabled: draft.enabled,
  }
}

// Validação leve (espelho do server). Retorna lista de erros; vazia = válida.
export function validateRule(draft: RuleDraft, meta: AutomationMeta): string[] {
  const errors: string[] = []
  if (!draft.name.trim()) errors.push('nome obrigatório')
  if (!meta.trigger_events.includes(draft.trigger_event)) errors.push('gatilho inválido')
  for (const c of draft.conditions) {
    if (!meta.fields.includes(c.field)) errors.push(`campo inválido: ${c.field || '(vazio)'}`)
    if (!meta.ops.includes(c.op)) errors.push(`operador inválido: ${c.op || '(vazio)'}`)
  }
  for (const a of draft.actions) {
    if (!meta.actions.includes(a.type)) errors.push(`ação inválida: ${a.type || '(vazio)'}`)
  }
  if (draft.actions.length === 0) errors.push('ao menos uma ação')
  return errors
}

export function isRuleValid(draft: RuleDraft, meta: AutomationMeta): boolean {
  return validateRule(draft, meta).length === 0
}
