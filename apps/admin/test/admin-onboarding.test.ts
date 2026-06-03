// #1G-a T1.F — testes determinísticos da lógica pura do console admin:
// (1) o campo numérico inicial que cada tipo de contrato exige (helper que o
//     formulário "novo contrato" usa para adaptar os campos visíveis);
// (2) os rótulos/cores de status reutilizados pelas páginas.
// Sem dependência de sidecar vivo.
import { describe, expect, it } from 'vitest'
import {
  CONTRACT_TYPES,
  initialFieldFor,
  statusColor,
  statusLabel,
  typeLabel,
} from '../shared/contracts'

describe('initialFieldFor — campo inicial adapta ao tipo', () => {
  it('hour_bank exige initial_hours', () => {
    const spec = initialFieldFor('hour_bank')
    expect(spec.field).toBe('initial_hours')
    expect(spec.unit).toBe('hours')
  })

  it('service_count exige initial_service_count', () => {
    const spec = initialFieldFor('service_count')
    expect(spec.field).toBe('initial_service_count')
    expect(spec.unit).toBe('count')
  })

  it.each(['credit_brl', 'credit_shared', 'closed_value', 'saas_product'])(
    '%s exige initial_amount_brl',
    (type) => {
      const spec = initialFieldFor(type)
      expect(spec.field).toBe('initial_amount_brl')
      expect(spec.unit).toBe('brl')
    },
  )

  it('tipo desconhecido cai no default initial_amount_brl', () => {
    expect(initialFieldFor('???').field).toBe('initial_amount_brl')
  })

  it('todos os 6 tipos congelados têm um spec válido', () => {
    expect(CONTRACT_TYPES).toHaveLength(6)
    for (const t of CONTRACT_TYPES) {
      const spec = initialFieldFor(t)
      expect(['initial_amount_brl', 'initial_hours', 'initial_service_count']).toContain(spec.field)
      expect(spec.label).toBeTruthy()
      expect(spec.step).toBeTruthy()
    }
  })
})

describe('rótulos de contrato', () => {
  it('traduz os tipos congelados para PT', () => {
    expect(typeLabel('hour_bank')).toBe('Banco de horas')
    expect(typeLabel('credit_brl')).toBe('Crédito (R$)')
  })

  it('tipo desconhecido retorna o próprio valor', () => {
    expect(typeLabel('mystery')).toBe('mystery')
  })

  it('status mapeia rótulo + cor', () => {
    expect(statusLabel('active')).toBe('Ativo')
    expect(statusColor('active')).toBe('success')
    expect(statusColor('expired')).toBe('error')
    expect(statusColor('weird')).toBe('neutral')
  })
})

// Espelha a montagem do corpo do POST /contracts: somente o campo inicial do
// tipo escolhido é enviado (mesma regra que a página aplica via initialFieldFor).
describe('montagem do corpo de contrato por tipo', () => {
  function buildBody(type: string, initialValue: number) {
    const spec = initialFieldFor(type)
    const body: Record<string, unknown> = { type }
    body[spec.field] = initialValue
    return body
  }

  it('hour_bank envia somente initial_hours', () => {
    const b = buildBody('hour_bank', 40)
    expect(b.initial_hours).toBe(40)
    expect(b.initial_amount_brl).toBeUndefined()
    expect(b.initial_service_count).toBeUndefined()
  })

  it('service_count envia somente initial_service_count', () => {
    const b = buildBody('service_count', 10)
    expect(b.initial_service_count).toBe(10)
    expect(b.initial_hours).toBeUndefined()
  })

  it('credit_brl envia somente initial_amount_brl', () => {
    const b = buildBody('credit_brl', 5000)
    expect(b.initial_amount_brl).toBe(5000)
    expect(b.initial_hours).toBeUndefined()
  })
})
