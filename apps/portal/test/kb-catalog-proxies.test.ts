import { afterEach, describe, expect, it, vi } from 'vitest'

// Spec #3 · V1/V2 — proxies server-side de base de conhecimento e catálogo de
// serviços. Mesmo harness de dashboard-metrics.test.ts/notifications-proxy.test.ts:
// stub dos globais Nitro/h3 e de sidecarFetch, import direto do handler.

afterEach(() => vi.unstubAllGlobals())

describe('GET /api/portal/kb/articles', () => {
  it('repassa q e category ao sidecar quando presentes', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getQuery', () => ({ q: 'senha', category: 'Acesso' }))
    const payload = { items: [], total: 0, limit: 20, offset: 0 }
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, data: payload, setCookie: [] })
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/kb/articles/index.get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith({}, '/v1/kb/articles?q=senha&category=Acesso')
  })

  it('sem query → repassa /v1/kb/articles sem querystring', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getQuery', () => ({}))
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, data: { items: [] }, setCookie: [] })
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/kb/articles/index.get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    await handler({})

    expect(fetchMock).toHaveBeenCalledWith({}, '/v1/kb/articles')
  })

  it('status != 200 → null (contrato de erro do proxy)', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getQuery', () => ({}))
    vi.stubGlobal('sidecarFetch', vi.fn().mockResolvedValue({ status: 503, data: null, setCookie: [] }))

    const mod = await import('../server/api/portal/kb/articles/index.get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toBeNull()
  })
})

describe('GET /api/portal/kb/articles/[slug]', () => {
  it('slug presente → repassa /v1/kb/articles/{slug}', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getRouterParam', () => 'como-resetar-senha')
    const payload = { id: '1', slug: 'como-resetar-senha', body_markdown: '# Título' }
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, data: payload, setCookie: [] })
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/kb/articles/[slug].get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith({}, '/v1/kb/articles/como-resetar-senha')
  })

  it('404 (não público/inexistente) → null', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getRouterParam', () => 'nao-existe')
    vi.stubGlobal('sidecarFetch', vi.fn().mockResolvedValue({ status: 404, data: null, setCookie: [] }))

    const mod = await import('../server/api/portal/kb/articles/[slug].get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toBeNull()
  })
})

describe('GET /api/portal/kb/categories', () => {
  it('repassa /v1/kb/categories e devolve a lista', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    const payload = [{ category: 'Acesso', count: 3 }]
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, data: payload, setCookie: [] })
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/kb/categories.get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith({}, '/v1/kb/categories')
  })
})

describe('GET /api/portal/catalog/items', () => {
  it('com category → repassa querystring', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getQuery', () => ({ category: 'Segurança' }))
    const payload = [{ id: 'a', name: 'Reset de senha' }]
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, data: payload, setCookie: [] })
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/catalog/items/index.get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith({}, '/v1/catalog/items?category=Seguran%C3%A7a')
  })

  it('sem category → repassa /v1/catalog/items sem querystring', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getQuery', () => ({}))
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, data: [], setCookie: [] })
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/catalog/items/index.get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    await handler({})

    expect(fetchMock).toHaveBeenCalledWith({}, '/v1/catalog/items')
  })
})

describe('GET /api/portal/catalog/items/[id]', () => {
  it('id UUID válido → repassa /v1/catalog/items/{id}', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    const setStatus = vi.fn()
    vi.stubGlobal('setResponseStatus', setStatus)
    const id = '3fa85f64-5717-4562-b3fc-2c963f66afa6'
    vi.stubGlobal('getRouterParam', () => id)
    const payload = { id, name: 'Reset de senha', znuny_queue: 'Suporte', znuny_service: 'Acesso', default_priority: '3 normal' }
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, data: payload, setCookie: [] })
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/catalog/items/[id].get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith({}, `/v1/catalog/items/${id}`)
  })

  it('id fora do formato uuid → 400 sem chamar o sidecar', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getRouterParam', () => '123')
    const fetchMock = vi.fn()
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/catalog/items/[id].get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('id ausente → 400', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getRouterParam', () => undefined)
    const fetchMock = vi.fn()
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/catalog/items/[id].get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    await handler({})

    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('404 (cross-tenant ou inativo) → null', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getRouterParam', () => '3fa85f64-5717-4562-b3fc-2c963f66afa6')
    vi.stubGlobal('sidecarFetch', vi.fn().mockResolvedValue({ status: 404, data: null, setCookie: [] }))

    const mod = await import('../server/api/portal/catalog/items/[id].get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toBeNull()
  })
})

describe('GET /api/portal/catalog/categories', () => {
  it('repassa /v1/catalog/categories e devolve a lista', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    const payload = [{ category: 'Segurança', count: 2 }]
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, data: payload, setCookie: [] })
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/catalog/categories.get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith({}, '/v1/catalog/categories')
  })
})
