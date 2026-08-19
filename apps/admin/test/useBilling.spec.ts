// R6 / T-R15.3 — regras da aba de faturamento. Lógica pura, sem servidor.
import { describe, expect, it } from 'vitest'
import {
  canCharge,
  canIssueNfe,
  carryOverSummary,
  chargeStatusLabel,
  chargeTotal,
  emptyCharge,
  nfeStatusLabel,
  timeWarning,
  validateCharge,
} from '../composables/useBilling'

describe('lançamento avulso', () => {
  it('exige contrato, descrição e quantidade', () => {
    const errors = validateCharge({ ...emptyCharge(), quantity: 0 })
    expect(errors).toContain('Escolha o contrato que vai receber o lançamento.')
    expect(errors).toContain('Descreva o lançamento — ele aparece na fatura do cliente.')
    expect(errors).toContain('A quantidade precisa ser maior que zero.')
  })

  it('aceita um lançamento completo', () => {
    expect(validateCharge({
      ...emptyCharge(),
      contract_id: 'c1',
      description: 'Deslocamento até o cliente',
      amount_brl: 80,
    })).toEqual([])
  })

  it('multiplica quantidade por valor', () => {
    expect(chargeTotal({ ...emptyCharge(), amount_brl: 80, quantity: 3 })).toBe(240)
  })

  it('avisa quando deslocamento vai comer banco de horas', () => {
    // O engano típico: R$ 80 de viagem descontando 1 h do cliente.
    const warn = timeWarning({ ...emptyCharge(), kind: 'travel', minutes: 60 })
    expect(warn).toContain('banco de horas')
  })

  it('não avisa em hora avulsa, que É tempo de propósito', () => {
    expect(timeWarning({ ...emptyCharge(), kind: 'ticket_work', minutes: 120 })).toBeNull()
  })

  it('não avisa em deslocamento sem minutos', () => {
    expect(timeWarning({ ...emptyCharge(), kind: 'travel', minutes: 0 })).toBeNull()
  })
})

describe('D-R — resumo do acúmulo', () => {
  it('diz claramente quando não acumula', () => {
    expect(carryOverSummary({ accumulate: false, capMinutes: null, expiresDays: null }))
      .toContain('se perde')
  })

  it('mostra o padrão: acumula sem teto e sem validade', () => {
    const text = carryOverSummary({ accumulate: true, capMinutes: null, expiresDays: null })
    expect(text).toContain('sem teto')
    expect(text).toContain('sem validade')
  })

  it('converte o teto de minutos para horas, que é como o operador pensa', () => {
    const text = carryOverSummary({ accumulate: true, capMinutes: 2400, expiresDays: 60 })
    expect(text).toContain('40.0 h')
    expect(text).toContain('60 dias')
  })
})

describe('T-R15.5 — cobrança e nota', () => {
  it('traduz o estado do Asaas', () => {
    expect(chargeStatusLabel('RECEIVED')).toBe('Pago')
    expect(chargeStatusLabel(null)).toBe('Sem cobrança emitida')
    // Estado desconhecido aparece cru em vez de sumir.
    expect(chargeStatusLabel('ALGO_NOVO')).toBe('ALGO_NOVO')
    expect(nfeStatusLabel('AUTHORIZED')).toBe('Autorizada')
    expect(nfeStatusLabel(undefined)).toBe('Nota não emitida')
  })

  it('só oferece nota depois do boleto', () => {
    expect(canIssueNfe({ asaas_payment_id: null })).toBe(false)
    expect(canIssueNfe({ asaas_payment_id: 'pay_1' })).toBe(true)
    expect(canIssueNfe({ asaas_payment_id: 'pay_1', nfe_status: 'SCHEDULED' })).toBe(false)
  })

  it('não oferece segundo boleto para a mesma fatura', () => {
    expect(canCharge({ status: 'open', total_cents: 1000, asaas_payment_id: 'pay_1' })).toBe(false)
  })

  it('não cobra fatura zerada nem terminal', () => {
    expect(canCharge({ status: 'open', total_cents: 0 })).toBe(false)
    expect(canCharge({ status: 'paid', total_cents: 1000 })).toBe(false)
    expect(canCharge({ status: 'void', total_cents: 1000 })).toBe(false)
    expect(canCharge({ status: 'open', total_cents: 1000 })).toBe(true)
  })
})
