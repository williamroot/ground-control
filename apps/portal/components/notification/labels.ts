// Rótulos, ícones e cores PT do centro de notificações (Spec #3 V3).
//
// H8 — cor SEMÂNTICA, nunca a cor da marca: cada `kind` tem que ler como
// "informação"/"alerta"/"erro" em QUALQUER marca de tenant. Mapa em .ts puro
// (testável sem montar componente Nuxt).

export type NotificationColor = 'success' | 'warning' | 'error' | 'info' | 'neutral'

export type NotificationKind
  = | 'ticket_update'
    | 'ticket_reply'
    | 'sla_warning'
    | 'sla_breach'
    | 'contract_alert'
    | 'invoice_issued'
    | 'system'

export interface NotificationKindMeta {
  label: string
  icon: string
  color: NotificationColor
}

const KIND_META: Record<NotificationKind, NotificationKindMeta> = {
  ticket_update: { label: 'Atualização de chamado', icon: 'i-lucide-ticket', color: 'info' },
  ticket_reply: { label: 'Resposta no chamado', icon: 'i-lucide-message-circle', color: 'info' },
  sla_warning: { label: 'Alerta de SLA', icon: 'i-lucide-alarm-clock', color: 'warning' },
  sla_breach: { label: 'SLA violado', icon: 'i-lucide-alarm-clock-off', color: 'error' },
  contract_alert: { label: 'Alerta de contrato', icon: 'i-lucide-file-warning', color: 'warning' },
  invoice_issued: { label: 'Fatura emitida', icon: 'i-lucide-receipt', color: 'info' },
  system: { label: 'Sistema', icon: 'i-lucide-settings', color: 'neutral' },
}

// `kind` desconhecido (ex.: notificação de uma versão futura do backend) cai
// aqui — nunca quebra a tela, nunca usa a cor da marca.
const FALLBACK_META: NotificationKindMeta = { label: 'Notificação', icon: 'i-lucide-bell', color: 'neutral' }

export function notificationKindMeta(kind: string): NotificationKindMeta {
  return (KIND_META as Record<string, NotificationKindMeta>)[kind] ?? FALLBACK_META
}

// Classes utilitárias ESTÁTICAS (strings literais completas — o scanner do
// Tailwind precisa vê-las assim para não purgar) para o acento visual do item
// não lido, uma por cor semântica.
export const NOTIFICATION_ACCENT_CLASSES: Record<NotificationColor, string> = {
  success: 'border-l-4 border-success bg-success/5',
  warning: 'border-l-4 border-warning bg-warning/5',
  error: 'border-l-4 border-error bg-error/5',
  info: 'border-l-4 border-info bg-info/5',
  neutral: 'border-l-4 border-neutral bg-neutral/5',
}

export function notificationAccentClass(kind: string): string {
  return NOTIFICATION_ACCENT_CLASSES[notificationKindMeta(kind).color]
}

// Ícone do item: fundo suave + texto na cor semântica. Mesma razão acima —
// strings literais completas, nada de `bg-${color}/10` interpolado (o
// scanner do Tailwind não resolve interpolação em runtime).
export const NOTIFICATION_ICON_CLASSES: Record<NotificationColor, string> = {
  success: 'bg-success/10 text-success',
  warning: 'bg-warning/10 text-warning',
  error: 'bg-error/10 text-error',
  info: 'bg-info/10 text-info',
  neutral: 'bg-neutral/10 text-neutral',
}

export function notificationIconClass(kind: string): string {
  return NOTIFICATION_ICON_CLASSES[notificationKindMeta(kind).color]
}

// Marcador de "não lida" (bolinha) — mesma cor semântica do kind, nunca a marca.
export const NOTIFICATION_DOT_CLASSES: Record<NotificationColor, string> = {
  success: 'bg-success',
  warning: 'bg-warning',
  error: 'bg-error',
  info: 'bg-info',
  neutral: 'bg-neutral',
}

export function notificationDotClass(kind: string): string {
  return NOTIFICATION_DOT_CLASSES[notificationKindMeta(kind).color]
}
