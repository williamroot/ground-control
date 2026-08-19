// R7 — regras da fila de aprovação. Lógica PURA, sem $fetch: a página chama,
// isto decide o que é válido e o que dizer.
//
// *"Todo ticket passa, quando essa chave tá habilitada, todo ticket passa por
// aqui e vai pra um aprovador."* (07:40)

export interface Approval {
  id: string
  znuny_ticket_id: number
  status: string
  requested_by: string
  approver_login: string | null
  reason: string | null
  created_at: string
}

export type Decision = 'approved' | 'rejected'

/** Só quem tem papel de aprovador (ou admin do portal) decide. */
export function canDecide(role: string | null | undefined): boolean {
  return role === 'approver' || role === 'admin'
}

/**
 * Reprovar exige motivo; aprovar, não.
 *
 * O motivo não é burocracia: ele vai como nota no próprio chamado, e é o que
 * o autor lê para saber o que fazer a seguir. Sem ele, o pedido morre sem
 * explicação e a pessoa reabre o mesmo chamado na semana seguinte.
 */
export function validateDecision(decision: Decision, reason: string): string[] {
  if (decision === 'rejected' && !reason.trim()) {
    return ['Explique por que o pedido não foi aprovado — o autor vai ler isso no chamado.']
  }
  return []
}

export function decisionLabel(decision: Decision): string {
  return decision === 'approved' ? 'Aprovar' : 'Reprovar'
}

export function statusLabel(status: string): string {
  switch (status) {
    case 'pending': return 'Aguardando decisão'
    case 'approved': return 'Aprovado'
    case 'rejected': return 'Reprovado'
    default: return status
  }
}

export function statusColor(status: string): 'warning' | 'success' | 'error' | 'neutral' {
  switch (status) {
    case 'pending': return 'warning'
    case 'approved': return 'success'
    case 'rejected': return 'error'
    default: return 'neutral'
  }
}

/**
 * Mensagem de erro em português para as recusas que o sidecar devolve.
 * 409 é o caso que mais confunde: dois aprovadores clicam quase juntos e o
 * segundo precisa entender que a decisão do primeiro valeu, não que falhou.
 */
export function decisionError(statusCode: number | undefined, detail?: string): string {
  if (statusCode === 409) return 'Este chamado já foi decidido por outra pessoa.'
  if (statusCode === 403) return 'Seu usuário não tem permissão para aprovar chamados.'
  if (statusCode === 404) return 'Chamado não encontrado na fila de aprovação.'
  return detail || 'Não foi possível registrar a decisão.'
}
