// Rótulos PT compartilhados de contrato (tipo/status) — DRY entre dashboard e detalhe.
export type StatusColor = 'success' | 'warning' | 'neutral' | 'error'
export type BadgeColor = StatusColor | 'info'

const TYPE_LABEL: Record<string, string> = {
  hour_bank: 'Banco de horas', credit_brl: 'Crédito (R$)', credit_shared: 'Crédito compartilhado',
  service_count: 'Pacote de serviços', closed_value: 'Valor fechado', saas_product: 'Assinatura',
}
const STATUS_META: Record<string, { label: string, color: StatusColor }> = {
  active: { label: 'Ativo', color: 'success' }, suspended: { label: 'Suspenso', color: 'warning' },
  expired: { label: 'Expirado', color: 'error' }, terminated: { label: 'Encerrado', color: 'neutral' },
  draft: { label: 'Rascunho', color: 'neutral' },
}

export function typeLabel(t: string): string { return TYPE_LABEL[t] ?? t }
export function statusLabel(s: string): string { return (STATUS_META[s] ?? { label: s }).label }
export function statusColor(s: string): StatusColor { return (STATUS_META[s] ?? { color: 'neutral' as const }).color }

// Faturas internas (#1P) — cores SEMÂNTICAS (H8): nunca a cor da marca.
// overdue=error, paid=success, open=info, void/draft=neutral.
const INVOICE_STATUS_META: Record<string, { label: string, color: BadgeColor }> = {
  draft: { label: 'Rascunho', color: 'neutral' },
  open: { label: 'Em aberto', color: 'info' },
  paid: { label: 'Paga', color: 'success' },
  overdue: { label: 'Vencida', color: 'error' },
  void: { label: 'Cancelada', color: 'neutral' },
}

export function invoiceStatusLabel(s: string): string {
  return (INVOICE_STATUS_META[s] ?? { label: s }).label
}
export function invoiceStatusColor(s: string): BadgeColor {
  return (INVOICE_STATUS_META[s] ?? { color: 'neutral' as const }).color
}

// Centavos (int) → 'R$ 1.234,56' (pt-BR). Usado nas tabelas de fatura.
export function moneyBRLFromCents(cents: number): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(cents / 100)
}
