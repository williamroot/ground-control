import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  debounce,
  isSearchableQuery,
  SEARCH_MIN_LENGTH,
  type SearchResults,
  searchSections,
  searchTotal,
} from '../shared/search'

// #3 V6 — busca global federada. Lógica pura (validação de `q`, debounce,
// agregação de contagem por seção), sem montar a página (composables Nuxt).

describe('isSearchableQuery: mínimo de 2 caracteres úteis', () => {
  it(`respeita SEARCH_MIN_LENGTH=${SEARCH_MIN_LENGTH}`, () => {
    expect(SEARCH_MIN_LENGTH).toBe(2)
  })
  it('1 caractere → não busca', () => {
    expect(isSearchableQuery('a')).toBe(false)
  })
  it('2 caracteres → busca', () => {
    expect(isSearchableQuery('ab')).toBe(true)
  })
  it('vazio/whitespace → não busca', () => {
    expect(isSearchableQuery('')).toBe(false)
    expect(isSearchableQuery('   ')).toBe(false)
  })
  it('espaços nas pontas não contam para o mínimo', () => {
    expect(isSearchableQuery(' a ')).toBe(false)
    expect(isSearchableQuery(' ab ')).toBe(true)
  })
})

describe('debounce: agrupa chamadas rápidas, mantém só a última', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('só chama fn uma vez após o silêncio, com o último argumento', () => {
    const fn = vi.fn()
    const d = debounce(fn, 300)
    d.run('a')
    d.run('ab')
    d.run('abc')
    expect(fn).not.toHaveBeenCalled()
    vi.advanceTimersByTime(299)
    expect(fn).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(fn).toHaveBeenCalledTimes(1)
    expect(fn).toHaveBeenCalledWith('abc')
  })

  it('cancel() impede a execução pendente', () => {
    const fn = vi.fn()
    const d = debounce(fn, 300)
    d.run('x')
    d.cancel()
    vi.advanceTimersByTime(300)
    expect(fn).not.toHaveBeenCalled()
  })

  it('chamadas espaçadas além do wait disparam mais de uma vez', () => {
    const fn = vi.fn()
    const d = debounce(fn, 300)
    d.run('a')
    vi.advanceTimersByTime(300)
    d.run('b')
    vi.advanceTimersByTime(300)
    expect(fn).toHaveBeenCalledTimes(2)
    expect(fn).toHaveBeenNthCalledWith(1, 'a')
    expect(fn).toHaveBeenNthCalledWith(2, 'b')
  })
})

function results(over: Partial<SearchResults> = {}): SearchResults {
  return { tickets: [], assets: [], kb: [], catalog: [], ...over }
}

const ITEM = { id: '1', title: 'x', subtitle: null, path: '/x' }

describe('searchSections: só as seções COM resultado, na ordem fixa', () => {
  it('null → nenhuma seção', () => {
    expect(searchSections(null)).toEqual([])
  })
  it('tudo vazio → nenhuma seção', () => {
    expect(searchSections(results())).toEqual([])
  })
  it('omite seções vazias, mantém as com item', () => {
    const r = results({ tickets: [ITEM], kb: [ITEM, ITEM] })
    const sections = searchSections(r)
    expect(sections.map(s => s.key)).toEqual(['tickets', 'kb'])
    expect(sections.find(s => s.key === 'kb')!.items).toHaveLength(2)
  })
  it('rótulos em PT: Chamados / Ativos / Base de Conhecimento / Catálogo', () => {
    const r = results({ tickets: [ITEM], assets: [ITEM], kb: [ITEM], catalog: [ITEM] })
    const labels = searchSections(r).map(s => s.label)
    expect(labels).toEqual(['Chamados', 'Ativos', 'Base de Conhecimento', 'Catálogo'])
  })
  it('preserva o path do item AS-IS (sem concatenar nada)', () => {
    const r = results({ kb: [{ id: 'kb-001', title: 'Artigo', subtitle: null, path: '/base-conhecimento/kb-001' }] })
    expect(searchSections(r)[0]!.items[0]!.path).toBe('/base-conhecimento/kb-001')
  })
})

describe('searchTotal: contagem agregada das 4 fontes', () => {
  it('null → 0', () => {
    expect(searchTotal(null)).toBe(0)
  })
  it('soma os itens de todas as seções', () => {
    const r = results({ tickets: [ITEM], assets: [ITEM, ITEM], kb: [], catalog: [ITEM] })
    expect(searchTotal(r)).toBe(4)
  })
})

describe('GET /api/portal/search (proxy)', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('repassa q ao sidecar (url-encoded) e devolve o payload em 200', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getQuery', () => ({ q: 'nota fiscal' }))
    const payload = results({ tickets: [ITEM] })
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, data: payload, setCookie: [] })
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/search.get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith({}, '/v1/search?q=nota%20fiscal')
  })

  it('sem q → repassa string vazia (o sidecar decide o 422)', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getQuery', () => ({}))
    const fetchMock = vi.fn().mockResolvedValue({ status: 422, data: null, setCookie: [] })
    vi.stubGlobal('sidecarFetch', fetchMock)

    const mod = await import('../server/api/portal/search.get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    await handler({})

    expect(fetchMock).toHaveBeenCalledWith({}, '/v1/search?q=')
  })

  it('status != 200 → null', async () => {
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('setResponseStatus', vi.fn())
    vi.stubGlobal('getQuery', () => ({ q: 'ab' }))
    vi.stubGlobal('sidecarFetch', vi.fn().mockResolvedValue({ status: 503, data: null, setCookie: [] }))

    const mod = await import('../server/api/portal/search.get')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})

    expect(out).toBeNull()
  })
})
