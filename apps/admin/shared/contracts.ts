// Lógica PURA de contrato compartilhada entre as páginas admin e os testes
// (em shared/ por causa da import-protection do Nuxt; importável por #shared).
// #1G-a T1.F — espelha os tipos CONGELADOS do sidecar (admin_contracts.py).

export type ContractType =
  | 'credit_brl'
  | 'credit_shared'
  | 'hour_bank'
  | 'service_count'
  | 'closed_value'
  | 'saas_product'

export const CONTRACT_TYPES: ContractType[] = [
  'credit_brl',
  'credit_shared',
  'hour_bank',
  'service_count',
  'closed_value',
  'saas_product',
]

const TYPE_LABEL: Record<ContractType, string> = {
  credit_brl: 'Crédito (R$)',
  credit_shared: 'Crédito compartilhado',
  hour_bank: 'Banco de horas',
  service_count: 'Pacote de serviços',
  closed_value: 'Valor fechado',
  saas_product: 'Assinatura (SaaS)',
}

export function typeLabel(t: string): string {
  return TYPE_LABEL[t as ContractType] ?? t
}

export type StatusColor = 'success' | 'warning' | 'neutral' | 'error' | 'primary'

const STATUS_META: Record<string, { label: string, color: StatusColor }> = {
  active: { label: 'Ativo', color: 'success' },
  suspended: { label: 'Suspenso', color: 'warning' },
  expired: { label: 'Expirado', color: 'error' },
  terminated: { label: 'Encerrado', color: 'neutral' },
  draft: { label: 'Rascunho', color: 'neutral' },
  pending: { label: 'Pendente', color: 'warning' },
}

export function statusLabel(s: string): string {
  return (STATUS_META[s] ?? { label: s }).label
}

export function statusColor(s: string): StatusColor {
  return (STATUS_META[s] ?? { color: 'neutral' as const }).color
}

// Faturas internas (#1P) — cores SEMÂNTICAS (H8): overdue=error, paid=success,
// open=info, void/draft=neutral. `info` é semântico do Nuxt UI, nunca a marca.
export type InvoiceBadgeColor = 'success' | 'warning' | 'neutral' | 'error' | 'info'

const INVOICE_STATUS_META: Record<string, { label: string, color: InvoiceBadgeColor }> = {
  draft: { label: 'Rascunho', color: 'neutral' },
  open: { label: 'Em aberto', color: 'info' },
  paid: { label: 'Paga', color: 'success' },
  overdue: { label: 'Vencida', color: 'error' },
  void: { label: 'Cancelada', color: 'neutral' },
}

export function invoiceStatusLabel(s: string): string {
  return (INVOICE_STATUS_META[s] ?? { label: s }).label
}
export function invoiceStatusColor(s: string): InvoiceBadgeColor {
  return (INVOICE_STATUS_META[s] ?? { color: 'neutral' as const }).color
}

export function moneyBRLFromCents(cents: number): string {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(cents / 100)
}

// Campo numérico inicial que cada tipo de contrato exige. O formulário de
// "novo contrato" mostra/exige SOMENTE este campo conforme o tipo escolhido:
//   hour_bank      → initial_hours (horas)
//   service_count  → initial_service_count (quantidade)
//   demais tipos   → initial_amount_brl (R$)
export type InitialAmountField =
  | 'initial_amount_brl'
  | 'initial_hours'
  | 'initial_service_count'

export interface InitialFieldSpec {
  field: InitialAmountField
  label: string
  unit: 'brl' | 'hours' | 'count'
  step: string
}

const INITIAL_FIELD: Record<ContractType, InitialFieldSpec> = {
  hour_bank: { field: 'initial_hours', label: 'Horas iniciais', unit: 'hours', step: '0.5' },
  service_count: { field: 'initial_service_count', label: 'Quantidade de serviços', unit: 'count', step: '1' },
  credit_brl: { field: 'initial_amount_brl', label: 'Valor inicial (R$)', unit: 'brl', step: '0.01' },
  credit_shared: { field: 'initial_amount_brl', label: 'Valor inicial (R$)', unit: 'brl', step: '0.01' },
  closed_value: { field: 'initial_amount_brl', label: 'Valor inicial (R$)', unit: 'brl', step: '0.01' },
  saas_product: { field: 'initial_amount_brl', label: 'Valor inicial (R$)', unit: 'brl', step: '0.01' },
}

// Helper PURO (unit-testado): qual campo inicial um tipo exige.
export function initialFieldFor(type: string): InitialFieldSpec {
  return INITIAL_FIELD[type as ContractType] ?? INITIAL_FIELD.credit_brl
}
