import { describe, expect, it } from 'vitest'
import {
  NOTIFICATION_ACCENT_CLASSES,
  NOTIFICATION_DOT_CLASSES,
  NOTIFICATION_ICON_CLASSES,
  notificationAccentClass,
  notificationDotClass,
  notificationIconClass,
  notificationKindMeta,
} from '../components/notification/labels'

// #3 V3 — mapa kind → ícone/cor do centro de notificações. Cores SEMÂNTICAS
// (H8): NUNCA a cor da marca — cada kind tem que ler como
// informação/alerta/erro em qualquer marca de tenant.

const SEMANTIC = new Set(['success', 'warning', 'error', 'info', 'neutral'])
const ALL_KINDS = [
  'ticket_update',
  'ticket_reply',
  'sla_warning',
  'sla_breach',
  'contract_alert',
  'invoice_issued',
  'system',
]

describe('notificationKindMeta: mapeia todos os kinds do contrato', () => {
  it('cobre os 7 kinds da Spec #3 V3', () => {
    for (const kind of ALL_KINDS) {
      const meta = notificationKindMeta(kind)
      expect(meta.label).toBeTruthy()
      expect(meta.icon).toMatch(/^i-lucide-/)
    }
  })

  it('sla_breach é mais severo (error) que sla_warning (warning)', () => {
    expect(notificationKindMeta('sla_warning').color).toBe('warning')
    expect(notificationKindMeta('sla_breach').color).toBe('error')
  })

  it('system usa neutral', () => {
    expect(notificationKindMeta('system').color).toBe('neutral')
  })

  it('kind desconhecido cai num fallback seguro, nunca quebra', () => {
    const meta = notificationKindMeta('algo_novo_do_backend')
    expect(meta.color).toBe('neutral')
    expect(meta.icon).toMatch(/^i-lucide-/)
  })

  it('só usa tokens semânticos (H8: nunca a cor da marca)', () => {
    for (const kind of [...ALL_KINDS, 'desconhecido']) {
      expect(SEMANTIC.has(notificationKindMeta(kind).color)).toBe(true)
    }
  })
})

describe('classes utilitárias por cor: só tokens semânticos, nada de --brand-*', () => {
  it('accent/icon/dot cobrem as 5 cores semânticas', () => {
    for (const color of SEMANTIC) {
      expect(NOTIFICATION_ACCENT_CLASSES).toHaveProperty(color)
      expect(NOTIFICATION_ICON_CLASSES).toHaveProperty(color)
      expect(NOTIFICATION_DOT_CLASSES).toHaveProperty(color)
    }
  })

  it('nenhuma classe referencia a cor da marca', () => {
    const all = [
      ...Object.values(NOTIFICATION_ACCENT_CLASSES),
      ...Object.values(NOTIFICATION_ICON_CLASSES),
      ...Object.values(NOTIFICATION_DOT_CLASSES),
    ]
    for (const cls of all) {
      expect(cls).not.toContain('--brand-primary')
      expect(cls).not.toContain('--brand-accent')
    }
  })

  it('notificationAccentClass/IconClass/DotClass resolvem pelo kind', () => {
    expect(notificationAccentClass('sla_breach')).toContain('border-error')
    expect(notificationIconClass('sla_breach')).toContain('text-error')
    expect(notificationDotClass('sla_breach')).toBe('bg-error')

    expect(notificationAccentClass('ticket_reply')).toContain('border-info')
    expect(notificationIconClass('invoice_issued')).toContain('text-info')
  })
})
