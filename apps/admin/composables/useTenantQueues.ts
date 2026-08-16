// Relacionamentos cliente↔fila (T-R5.4, R5 do vídeo do Kleber). Lógica PURA.
//
// *"Aqui a gente vai falar quais filas de atendimento o cara vai ter acesso.
// Então a gente tem uma fila padrão. Tudo que entra por e-mail vem pra essa
// fila."* (04:03)
//
// A validação aqui espelha a do sidecar de propósito: a verdade é o 422 dele
// (que ainda valida cada id contra a lista viva do Znuny), mas o operador não
// precisa de um round-trip para saber que esqueceu de marcar a padrão.

export interface QueueOption {
  id: number
  name: string
  group_id?: number | null
  group_name?: string | null
}

export interface QueueSelection {
  id: number
  is_default: boolean
}

export interface TenantQueue {
  queue_id: number
  queue_name: string
  is_default: boolean
  group_id: number | null
  group_name: string | null
}

export function selectionFromTenantQueues(rows: TenantQueue[]): QueueSelection[] {
  return rows.map(r => ({ id: r.queue_id, is_default: r.is_default }))
}

/** Erros em português. Lista vazia = pode salvar. */
export function validateQueueSelection(selection: QueueSelection[]): string[] {
  const errors: string[] = []
  if (selection.length === 0) {
    errors.push('Selecione ao menos uma fila.')
    return errors
  }
  const defaults = selection.filter(s => s.is_default)
  if (defaults.length === 0) errors.push('Marque uma fila como padrão.')
  if (defaults.length > 1) errors.push('Só uma fila pode ser a padrão.')
  const ids = selection.map(s => s.id)
  if (new Set(ids).size !== ids.length) errors.push('Fila repetida na seleção.')
  return errors
}

/**
 * Marcar uma fila como padrão desmarca a anterior — no cliente, para a tela
 * nunca chegar a montar um estado que o banco recusaria (o índice parcial
 * único `ux_tenant_queue_default` permite no máximo uma por cliente).
 */
export function setDefault(selection: QueueSelection[], id: number): QueueSelection[] {
  return selection.map(s => ({ ...s, is_default: s.id === id }))
}

/** Alterna a fila na seleção. Tirar a fila padrão deixa a seleção sem padrão. */
export function toggleQueue(selection: QueueSelection[], id: number): QueueSelection[] {
  const found = selection.find(s => s.id === id)
  if (found) return selection.filter(s => s.id !== id)
  return [...selection, { id, is_default: false }]
}

/** Corpo do PUT: ordenado por id e sem duplicata, para o diff de auditoria ser estável. */
export function buildQueuesPayload(selection: QueueSelection[]): {
  queues: { queue_id: number, is_default: boolean }[]
} {
  const byId = new Map<number, boolean>()
  for (const s of selection) byId.set(s.id, s.is_default || (byId.get(s.id) ?? false))
  return {
    queues: [...byId.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([id, is_default]) => ({ queue_id: id, is_default })),
  }
}

/** "suporte (3 agentes)" — quem atende a fila, para a coluna do aceite A5.5. */
export function servedByLabel(
  groupName: string | null | undefined,
  agentCount: number | null | undefined,
): string {
  if (!groupName) return '—'
  if (agentCount === null || agentCount === undefined) return groupName
  return `${groupName} (${agentCount} ${agentCount === 1 ? 'agente' : 'agentes'})`
}
