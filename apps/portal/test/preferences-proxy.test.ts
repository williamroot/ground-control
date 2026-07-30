import { afterEach, describe, expect, it, vi } from 'vitest'

// #3 V3 — proxies server-side de /me/preferences. Mesmo harness de
// dashboard-metrics.test.ts / notifications-proxy.test.ts. `setResponseStatus`
// é stubado (necessário p/ o módulo carregar) mas não é asserido diretamente
// — o contrato observável é o retorno (`out`) e a chamada a `sidecarFetch`.

afterEach(() => vi.unstubAllGlobals())

describe('GET /api/portal/me/preferences', () => {
  it('200 → devolve o payload', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    const payload = {
      theme: 'system',
      email_notifications: true,
      sla_alerts: true,
      ticket_updates: true,
      contract_alerts: true,
      invoice_alerts: true,
      weekly_report: false,
    }
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, data: payload, setCookie: [] })
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/me/preferences.get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith({}, '/v1/me/preferences')
  })

  it('status != 200 → null', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('sidecarFetch', vi.fn().mockResolvedValue({ status: 401, data: null, setCookie: [] }))

    const mod = await import('../server/api/portal/me/preferences.get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toBeNull()
  })
})

describe('PUT /api/portal/me/preferences', () => {
  it('repassa o corpo ao sidecar e devolve o objeto salvo (200)', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('readBody', vi.fn().mockResolvedValue({ theme: 'dark' }))
    const saved = { theme: 'dark', email_notifications: true }
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, data: saved, setCookie: [] })
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/me/preferences.put')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(fetchMock).toHaveBeenCalledWith({}, '/v1/me/preferences', { method: 'PUT', body: { theme: 'dark' } })
    expect(out).toEqual(saved)
  })

  it('422 do sidecar (enum inválido) é propagado no corpo, não mascarado', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('readBody', vi.fn().mockResolvedValue({ theme: 'roxo' }))
    vi.stubGlobal('sidecarFetch', vi.fn().mockResolvedValue({ status: 422, data: { detail: 'invalid theme' }, setCookie: [] }))

    const mod = await import('../server/api/portal/me/preferences.put')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toEqual({ detail: 'invalid theme' })
  })
})
