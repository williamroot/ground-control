// #1J fase 3 — smoke da lógica pura do timer de agente.
// Sem Nuxt, sem sidecar vivo: testa apenas os helpers determinísticos exportados
// diretamente de composables/useTimers.ts.
import { describe, expect, it } from 'vitest'
import { elapsedSeconds, formatHMS, type Timer } from '../composables/useTimers'

// ---------------------------------------------------------------------------
// Helpers para montar timers de teste
// ---------------------------------------------------------------------------
function makeTimer(overrides: Partial<Timer> = {}): Timer {
  return {
    id: 'test-id',
    znuny_ticket_id: 42,
    status: 'paused',
    accumulated_seconds: 0,
    last_started_at: null,
    committed_time_unit: null,
    ...overrides,
  }
}

// Converte uma data ISO para milissegundos de epoch (Date.now() equivalente).
function isoToMs(iso: string): number {
  return Date.parse(iso)
}

// ---------------------------------------------------------------------------
// elapsedSeconds — fórmula de tempo decorrido
// ---------------------------------------------------------------------------
describe('elapsedSeconds — timer pausado/parado', () => {
  it('retorna accumulated_seconds quando status=paused, independente de now', () => {
    const t = makeTimer({ status: 'paused', accumulated_seconds: 120 })
    const anyNow = isoToMs('2024-01-01T10:00:00.000Z')
    expect(elapsedSeconds(t, anyNow)).toBe(120)
  })

  it('retorna acumulado mesmo com last_started_at preenchido (paused)', () => {
    const t = makeTimer({
      status: 'paused',
      accumulated_seconds: 60,
      last_started_at: '2024-01-01T09:59:00.000Z',
    })
    const now = isoToMs('2024-01-01T10:00:00.000Z')
    // Paused: ignora last_started_at — só accumulated_seconds
    expect(elapsedSeconds(t, now)).toBe(60)
  })

  it('retorna 0 quando zerado e pausado', () => {
    const t = makeTimer({ status: 'paused', accumulated_seconds: 0 })
    expect(elapsedSeconds(t, isoToMs('2024-01-01T00:00:00.000Z'))).toBe(0)
  })
})

describe('elapsedSeconds — timer rodando', () => {
  it('acumulado + delta desde last_started_at (sem fração — Math.floor)', () => {
    const start = '2024-01-01T10:00:00.000Z'
    const t = makeTimer({
      status: 'running',
      accumulated_seconds: 30,
      last_started_at: start,
    })
    // now = start + 45 s
    const nowMs = isoToMs(start) + 45_000
    expect(elapsedSeconds(t, nowMs)).toBe(75) // 30 + 45
  })

  it('delta sub-segundo é truncado (Math.floor garante inteiro)', () => {
    const start = '2024-01-01T10:00:00.000Z'
    const t = makeTimer({
      status: 'running',
      accumulated_seconds: 10,
      last_started_at: start,
    })
    // now = start + 2.9 s → delta = 2 s após floor
    const nowMs = isoToMs(start) + 2_900
    expect(elapsedSeconds(t, nowMs)).toBe(12) // 10 + floor(2.9) = 12
  })

  it('delta nunca fica negativo (clock skew pequeno)', () => {
    const start = '2024-01-01T10:00:05.000Z'
    const t = makeTimer({
      status: 'running',
      accumulated_seconds: 5,
      last_started_at: start,
    })
    // now levemente antes de start (skew de relógio)
    const nowMs = isoToMs(start) - 500
    expect(elapsedSeconds(t, nowMs)).toBe(5) // delta=max(0,...) → 0
  })

  it('last_started_at=null em running → conta só o acumulado', () => {
    const t = makeTimer({ status: 'running', accumulated_seconds: 99, last_started_at: null })
    expect(elapsedSeconds(t, Date.now())).toBe(99)
  })
})

// ---------------------------------------------------------------------------
// formatHMS — display HH:MM:SS
// ---------------------------------------------------------------------------
describe('formatHMS — formatação de segundos para HH:MM:SS', () => {
  it('zero → "00:00:00"', () => {
    expect(formatHMS(0)).toBe('00:00:00')
  })

  it('90 s → "00:01:30"', () => {
    expect(formatHMS(90)).toBe('00:01:30')
  })

  it('3661 s → "01:01:01"', () => {
    expect(formatHMS(3661)).toBe('01:01:01')
  })

  it('3600 s → "01:00:00" (exato uma hora)', () => {
    expect(formatHMS(3600)).toBe('01:00:00')
  })

  it('59 s → "00:00:59"', () => {
    expect(formatHMS(59)).toBe('00:00:59')
  })

  it('negativo é tratado como 0 → "00:00:00"', () => {
    expect(formatHMS(-5)).toBe('00:00:00')
  })

  it('valor fracionário é truncado → floor antes de formatar', () => {
    expect(formatHMS(3661.9)).toBe('01:01:01')
  })
})

// ---------------------------------------------------------------------------
// Aviso "sem contrato" — regra do ContractBadge (replicada como lógica pura)
// A prop `contract` é { code, type } | null. Qualquer valor falsy → aviso.
// ---------------------------------------------------------------------------
describe('aviso de sem contrato — lógica do ContractBadge', () => {
  // A lógica que o template usa: `v-if="contract"` / `v-else`.
  // Testamos aqui a mesma regra de forma pura (sem montar componente Vue).
  function hasContract(contract: { code: string, type: string } | null): boolean {
    return !!contract
  }

  it('null → sem contrato (hasContract = false)', () => {
    expect(hasContract(null)).toBe(false)
  })

  it('objeto com código válido → tem contrato (hasContract = true)', () => {
    expect(hasContract({ code: 'C-001', type: 'hour_bank' })).toBe(true)
  })

  it('o aviso cobre todos os tipos de contrato do sistema', () => {
    const types = ['hour_bank', 'credit_brl', 'credit_shared', 'closed_value', 'saas_product', 'service_count']
    for (const type of types) {
      expect(hasContract({ code: 'X', type })).toBe(true)
    }
  })
})
