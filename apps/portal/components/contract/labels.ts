// Rótulos PT compartilhados de contrato (tipo/status) — DRY entre dashboard e detalhe.
export type StatusColor = 'success' | 'warning' | 'neutral' | 'error'

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
