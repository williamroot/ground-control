import { afterEach, describe, expect, it, vi } from 'vitest'

// #3 V3 — proxies server-side de notificações. Mesmo harness de
// dashboard-metrics.test.ts: stub dos globais Nitro/h3 (defineEventHandler já
// vem do setup.ts) e de sidecarFetch, import direto do handler.
//
// Nota: `setResponseStatus` é stubado (globals Nitro precisam existir para o
// módulo carregar) mas NÃO é asserido diretamente — mesmo padrão de
// dashboard-metrics.test.ts. O contrato observável e estável do proxy é o
// retorno (`out`) e a chamada a `sidecarFetch`.

afterEach(() => vi.unstubAllGlobals())

describe('GET /api/portal/notifications', () => {
  it('repassa status/limit/offset ao sidecar e devolve o payload em 200', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getQuery', () => ({ status: 'unread', limit: '20', offset: '0' }))
    const payload = { items: [], total: 0, unread: 0, limit: 20, offset: 0 }
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, data: payload, setCookie: [] })
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/notifications/index.get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith({}, '/v1/notifications?status=unread&limit=20&offset=0')
  })

  it('sem query → repassa /v1/notifications sem querystring', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getQuery', () => ({}))
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, data: { items: [] }, setCookie: [] })
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/notifications/index.get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    await handler({})

    expect(fetchMock).toHaveBeenCalledWith({}, '/v1/notifications')
  })

  it('status != 200 → null (contrato de erro do proxy)', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getQuery', () => ({}))
    vi.stubGlobal('sidecarFetch', vi.fn().mockResolvedValue({ status: 401, data: null, setCookie: [] }))

    const mod = await import('../server/api/portal/notifications/index.get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toBeNull()
  })
})

describe('POST /api/portal/notifications/[id]/read', () => {
  it('id UUID válido → repassa ao sidecar (204 -> body null)', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    const id = '3fa85f64-5717-4562-b3fc-2c963f66afa6'
    vi.stubGlobal('getRouterParam', () => id)
    const fetchMock = vi.fn().mockResolvedValue({ status: 204, data: null, setCookie: [] })
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/notifications/[id]/read.post')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(fetchMock).toHaveBeenCalledWith({}, `/v1/notifications/${id}/read`, { method: 'POST' })
    expect(out).toBeNull()
  })

  it('id fora do formato UUID → não chama o sidecar (guard de 400)', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getRouterParam', () => '123')
    const fetchMock = vi.fn()
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/notifications/[id]/read.post')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('id ausente → não chama o sidecar (guard de 400)', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getRouterParam', () => undefined)
    const fetchMock = vi.fn()
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/notifications/[id]/read.post')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('POST /api/portal/notifications/read-all', () => {
  it('repassa ao sidecar e devolve {updated:n}', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, data: { updated: 3 }, setCookie: [] })
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/notifications/read-all.post')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(fetchMock).toHaveBeenCalledWith({}, '/v1/notifications/read-all', { method: 'POST' })
    expect(out).toEqual({ updated: 3 })
  })
})
