// Spec #3, V6 — formatação pura das sondas de GET /admin/system/health.
import { describe, expect, it } from 'vitest'
import {
  formatDateTime,
  formatLatency,
  HEALTH_CARDS,
  probeStatus,
  probeStatusColor,
  probeStatusLabel,
} from '../composables/useSystemHealth'

describe('probeStatus', () => {
  it('ok=true -> ok', () => {
    expect(probeStatus({ ok: true, latency_ms: 3 })).toBe('ok')
  })

  it('ok=false -> error, mesmo com message', () => {
    expect(probeStatus({ ok: false, message: 'timeout' })).toBe('error')
  })

  it('enabled=false -> disabled, mesmo sem "ok" (caso Asaas do contrato)', () => {
    expect(probeStatus({ enabled: false })).toBe('disabled')
  })

  it('sonda ausente -> unknown', () => {
    expect(probeStatus(undefined)).toBe('unknown')
    expect(probeStatus(null)).toBe('unknown')
  })
})

describe('probeStatusColor/Label', () => {
  it('mapeia os 4 estados para cor e rótulo semânticos', () => {
    expect(probeStatusColor('ok')).toBe('success')
    expect(probeStatusColor('error')).toBe('error')
    expect(probeStatusColor('disabled')).toBe('neutral')
    expect(probeStatusColor('unknown')).toBe('warning')

    expect(probeStatusLabel('ok')).toBe('Operacional')
    expect(probeStatusLabel('error')).toBe('Com falha')
    expect(probeStatusLabel('disabled')).toBe('Desativado')
    expect(probeStatusLabel('unknown')).toBe('Desconhecido')
  })
})

describe('formatLatency', () => {
  it('formata ms quando presente', () => {
    expect(formatLatency(120)).toBe('120 ms')
  })

  it('null/undefined/NaN não formatam', () => {
    expect(formatLatency(null)).toBeNull()
    expect(formatLatency(undefined)).toBeNull()
    expect(formatLatency(Number.NaN)).toBeNull()
  })
})

describe('formatDateTime', () => {
  it('formata ISO em pt-BR quando presente', () => {
    expect(formatDateTime('2026-06-24T21:29:46Z')).toBe(
      new Date('2026-06-24T21:29:46Z').toLocaleString('pt-BR'),
    )
  })

  it('null/undefined/inválido não formatam', () => {
    expect(formatDateTime(null)).toBeNull()
    expect(formatDateTime(undefined)).toBeNull()
    expect(formatDateTime('not-a-date')).toBeNull()
  })
})

describe('HEALTH_CARDS', () => {
  it('cobre as 5 sondas do contrato (db, znuny_gi, worker, ai, asaas)', () => {
    expect(HEALTH_CARDS.map(c => c.key)).toEqual(['db', 'znuny_gi', 'worker', 'ai', 'asaas'])
  })
})
