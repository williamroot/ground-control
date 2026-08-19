// R6 / T-R15.3 / T-R3.2 — lógica PURA da aba de faturamento. Sem $fetch aqui:
// a página faz a chamada, isto decide o que é válido, o que rotular e o que
// avisar. É o que torna a regra testável sem subir servidor.

export interface ChargeKindOption {
  value: string
  label: string
  /** Minutos entram no banco de horas; deslocamento e despesa, não. */
  countsAsTime: boolean
}

/**
 * Tipos de lançamento avulso, na ordem em que o operador pensa neles.
 * Espelha `ALLOWED_KINDS` do sidecar — o 422 dele é a verdade, mas o seletor
 * não pode oferecer o que ele recusa.
 */
export const CHARGE_KINDS: ChargeKindOption[] = [
  { value: 'travel', label: 'Deslocamento', countsAsTime: false },
  { value: 'ticket_work', label: 'Hora avulsa', countsAsTime: true },
  { value: 'service_item', label: 'Item de catálogo', countsAsTime: false },
  { value: 'expense', label: 'Despesa', countsAsTime: false },
]

export function chargeKindLabel(kind: string): string {
  return CHARGE_KINDS.find(k => k.value === kind)?.label ?? kind
}

export interface ChargeDraft {
  contract_id: string
  kind: string
  description: string
  amount_brl: number
  quantity: number
  minutes: number
  occurred_on: string
}

export function emptyCharge(): ChargeDraft {
  return {
    contract_id: '',
    kind: 'travel',
    description: '',
    amount_brl: 0,
    quantity: 1,
    minutes: 0,
    occurred_on: new Date().toISOString().slice(0, 10),
  }
}

/** Erros em português. Lista vazia = pode enviar. */
export function validateCharge(draft: ChargeDraft): string[] {
  const errors: string[] = []
  if (!draft.contract_id) errors.push('Escolha o contrato que vai receber o lançamento.')
  if (!CHARGE_KINDS.some(k => k.value === draft.kind)) errors.push('Tipo de lançamento inválido.')
  if (!draft.description.trim()) {
    // O texto aparece na fatura do cliente; em branco vira uma linha muda.
    errors.push('Descreva o lançamento — ele aparece na fatura do cliente.')
  }
  if (!(draft.quantity > 0)) errors.push('A quantidade precisa ser maior que zero.')
  if (draft.amount_brl < 0) errors.push('O valor não pode ser negativo.')
  if (draft.minutes < 0) errors.push('Os minutos não podem ser negativos.')
  return errors
}

/** Total que vai para a fatura — quantidade × valor unitário. */
export function chargeTotal(draft: ChargeDraft): number {
  return Math.round(draft.amount_brl * draft.quantity * 100) / 100
}

/**
 * Aviso quando o lançamento vai consumir franquia de hora sem o operador ter
 * pedido isso. Deslocamento com minutos preenchidos é o engano típico: R$ 80
 * de viagem comendo 1 h do banco do cliente.
 */
export function timeWarning(draft: ChargeDraft): string | null {
  const kind = CHARGE_KINDS.find(k => k.value === draft.kind)
  if (!kind || kind.countsAsTime) return null
  if (draft.minutes > 0) {
    return `${kind.label} com minutos preenchidos vai descontar do banco de horas do cliente.`
  }
  return null
}

// ── D-Q / D-R: como a tela explica as duas decisões ────────────────────────

export function billingPeriodLabel(period: string): string {
  return period === 'cycle'
    ? 'Valor por fechamento (cobra 1× por ciclo)'
    : 'Valor mensal (ciclo trimestral cobra 3×)'
}

export function carryOverSummary(opts: {
  accumulate: boolean
  capMinutes: number | null
  expiresDays: number | null
}): string {
  if (!opts.accumulate) return 'Não acumula — o saldo não usado se perde no fim do ciclo.'
  const parts: string[] = ['Acumula entre ciclos']
  parts.push(opts.capMinutes ? `teto de ${(opts.capMinutes / 60).toFixed(1)} h` : 'sem teto')
  parts.push(opts.expiresDays ? `validade de ${opts.expiresDays} dias` : 'sem validade')
  return `${parts[0]}, ${parts.slice(1).join(', ')}.`
}

// ── T-R15.5: estado da cobrança no Asaas ───────────────────────────────────

const CHARGE_STATUS_PT: Record<string, string> = {
  PENDING: 'Aguardando pagamento',
  RECEIVED: 'Pago',
  CONFIRMED: 'Pagamento confirmado',
  OVERDUE: 'Vencido',
  REFUNDED: 'Estornado',
  PAYMENT_RECEIVED: 'Pago',
  PAYMENT_CONFIRMED: 'Pagamento confirmado',
  PAYMENT_OVERDUE: 'Vencido',
}

export function chargeStatusLabel(status: string | null | undefined): string {
  if (!status) return 'Sem cobrança emitida'
  return CHARGE_STATUS_PT[status] ?? status
}

const NFE_STATUS_PT: Record<string, string> = {
  SCHEDULED: 'Agendada',
  SYNCHRONIZED: 'Sincronizada',
  AUTHORIZED: 'Autorizada',
  PROCESSING_CANCELLATION: 'Cancelamento em andamento',
  CANCELED: 'Cancelada',
  CANCELLATION_DENIED: 'Cancelamento negado',
  ERROR: 'Erro na emissão',
}

export function nfeStatusLabel(status: string | null | undefined): string {
  if (!status) return 'Nota não emitida'
  return NFE_STATUS_PT[status] ?? status
}

/**
 * A nota fiscal pendura numa cobrança do Asaas, então só faz sentido oferecer
 * o botão depois de o boleto existir. Sem isto, o operador clicaria em "emitir
 * nota" e receberia um 422 sem entender a ordem.
 */
export function canIssueNfe(invoice: { asaas_payment_id?: string | null, nfe_status?: string | null }): boolean {
  return Boolean(invoice.asaas_payment_id) && !invoice.nfe_status
}

export function canCharge(invoice: {
  status: string
  total_cents: number
  asaas_payment_id?: string | null
}): boolean {
  if (invoice.asaas_payment_id) return false
  if (invoice.total_cents <= 0) return false
  return invoice.status !== 'paid' && invoice.status !== 'void'
}
