import { describe, expect, it, vi } from 'vitest'
import {
  csatBars,
  type DashboardMetrics,
  stateTone,
  ticketStateSegments,
  ticketVolumePoints,
} from '../shared/metrics'

// #1O — indicadores do dashboard.
//
// HARNESS: mesmo padrão dos outros testes do portal (lógica pura + proxy stub),
// SEM montar a page (que usa <script setup>/composables Nuxt indisponíveis sem
// boot). Cobre:
//   ✓ proxy /api/portal/dashboard/metrics repassa o status do sidecar
//   ✓ helpers que montam os charts a partir do payload (donut semântico H8,
//     área de volume na marca, barras de CSAT)

const PAYLOAD: DashboardMetrics = {
  period_days: 30,
  tickets: {
    by_state: { open: 3, 'closed successful': 7, 'pending reminder': 0 },
    by_priority: { '3 normal': 8 },
    by_day: [
      { date: '2026-06-01', count: 4 },
      { date: '2026-06-02', count: 6 },
    ],
    sla_breached: 2,
    sla_at_risk: 1,
    total: 10,
  },
  csat: { avg: 4.33, count: 3, distribution: { 1: 0, 2: 0, 3: 1, 4: 0, 5: 2 } },
  hours: { total_minutes: 90, total_hours: 1.5 },
  balance: { contract_count: 1, contracts: [], low_balance_alerts: [] },
}

describe('proxy /api/portal/dashboard/metrics', () => {
  it('repassa o status do sidecar (200 -> data, !=200 -> null)', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getQuery', () => ({ period: '30d' }))
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, data: PAYLOAD, setCookie: [] })
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/dashboard/metrics.get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>

    const ok = await handler({})
    expect(ok).toEqual(PAYLOAD)
    // ?period repassado ao sidecar
    expect(fetchMock).toHaveBeenCalledWith({}, '/v1/dashboard/metrics?period=30d')

    fetchMock.mockResolvedValueOnce({ status: 403, data: null, setCookie: [] })
    const forbidden = await handler({})
    // status != 200 -> propaga o status (body null) ao invés de mascarar como 200.
    expect(forbidden).toBeNull()

    vi.unstubAllGlobals()
  })
})

describe('stateTone: estados -> tom SEMÂNTICO (H8, nunca a marca)', () => {
  it('closed/resolved -> success', () => {
    expect(stateTone('closed successful')).toBe('success')
    expect(stateTone('resolved')).toBe('success')
  })
  it('pending/wait -> warning', () => {
    expect(stateTone('pending reminder')).toBe('warning')
  })
  it('open/new -> info', () => {
    expect(stateTone('open')).toBe('info')
    expect(stateTone('new')).toBe('info')
  })
  it('desconhecido -> neutral', () => {
    expect(stateTone('qualquer')).toBe('neutral')
  })
})

describe('helpers de chart a partir do payload', () => {
  it('ticketStateSegments: 1 fatia por estado com value>0, com tom semântico', () => {
    const segs = ticketStateSegments(PAYLOAD.tickets)
    // open + closed successful (pending=0 é filtrado)
    expect(segs).toHaveLength(2)
    const closed = segs.find(s => s.label === 'closed successful')!
    expect(closed.tone).toBe('success')
    expect(closed.value).toBe(7)
  })
  it('ticketVolumePoints: pontos {bucket,value} para a area chart', () => {
    const pts = ticketVolumePoints(PAYLOAD.tickets)
    expect(pts).toEqual([
      { bucket: '2026-06-01', value: 4 },
      { bucket: '2026-06-02', value: 6 },
    ])
  })
  it('tickets=null (GI fora do ar) -> arrays vazios (failure-soft)', () => {
    expect(ticketStateSegments(null)).toEqual([])
    expect(ticketVolumePoints(null)).toEqual([])
  })
  it('csatBars: sempre 5 barras (1..5) na ordem', () => {
    const bars = csatBars(PAYLOAD.csat)
    expect(bars).toHaveLength(5)
    expect(bars[4]).toEqual({ label: '5', value: 2 })
    expect(bars[2]).toEqual({ label: '3', value: 1 })
    expect(bars[0]).toEqual({ label: '1', value: 0 })
  })
})
