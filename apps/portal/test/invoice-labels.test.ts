import { describe, expect, it } from 'vitest'
import {
  invoiceStatusColor,
  invoiceStatusLabel,
  moneyBRLFromCents,
} from '../components/contract/labels'

// Cores SEMÂNTICAS (H8): nunca a cor da marca. overdue=error, paid=success,
// open=info, void=neutral.
const SEMANTIC = new Set(['success', 'warning', 'error', 'info', 'neutral'])

describe('invoiceStatusColor: cores semânticas do status da fatura', () => {
  it('overdue → error', () => {
    expect(invoiceStatusColor('overdue')).toBe('error')
  })
  it('paid → success', () => {
    expect(invoiceStatusColor('paid')).toBe('success')
  })
  it('open → info', () => {
    expect(invoiceStatusColor('open')).toBe('info')
  })
  it('void → neutral', () => {
    expect(invoiceStatusColor('void')).toBe('neutral')
  })
  it('draft → neutral', () => {
    expect(invoiceStatusColor('draft')).toBe('neutral')
  })
  it('desconhecido → neutral (nunca a marca)', () => {
    expect(invoiceStatusColor('xyz')).toBe('neutral')
  })
  it('só usa tokens semânticos (H8)', () => {
    for (const s of ['open', 'paid', 'overdue', 'void', 'draft', 'xyz']) {
      expect(SEMANTIC.has(invoiceStatusColor(s))).toBe(true)
    }
  })
})

describe('invoiceStatusLabel: rótulos PT', () => {
  it('mapeia os status', () => {
    expect(invoiceStatusLabel('open')).toBe('Em aberto')
    expect(invoiceStatusLabel('paid')).toBe('Paga')
    expect(invoiceStatusLabel('overdue')).toBe('Vencida')
    expect(invoiceStatusLabel('void')).toBe('Cancelada')
  })
  it('fallback p/ o próprio valor', () => {
    expect(invoiceStatusLabel('weird')).toBe('weird')
  })
})

describe('moneyBRLFromCents: centavos → BRL pt-BR', () => {
  it('formata milhares com separadores corretos', () => {
    expect(moneyBRLFromCents(35000)).toBe('R$ 350,00')
    expect(moneyBRLFromCents(120050)).toBe('R$ 1.200,50')
    expect(moneyBRLFromCents(5)).toBe('R$ 0,05')
  })
})
