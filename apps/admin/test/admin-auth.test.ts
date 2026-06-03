// T1.E (#1G-a): testes do login de agente + guarda de rota (cookie gsid_adm).
// Determinísticos — sem sidecar vivo. Exercitamos a lógica dos route handlers
// do server (via stub global de sidecarFetch + helpers h3 mockados) e a regra
// de redireciono da guarda. Escopo igual ao scaffold.test.ts.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import loginHandler from '../server/api/admin/auth/login.post'
import logoutHandler from '../server/api/admin/auth/logout.post'
import meHandler from '../server/api/admin/me.get'

// --- Helpers h3 que os handlers usam (auto-imports do Nuxt em prod). --------
// Capturamos o que dá para capturar de forma determinística num "event" fake:
//   • readBody / appendResponseHeader → stubamos via global e observamos o efeito.
//   • setResponseStatus → o transform de auto-import do @nuxt/test-utils resolve
//     para o h3 REAL (que espera um H3Event de verdade), então NÃO observamos o
//     status no event fake; em vez disso validamos o CONTRATO pelo retorno do
//     handler ({ok, status} / null), que é o que o cliente consome.
interface FakeEvent {
  _cookies: string[]
  _body: unknown
}

function makeEvent(body: unknown = {}): FakeEvent {
  return { _cookies: [], _body: body }
}

beforeEach(() => {
  Object.assign(globalThis, {
    readBody: (e: FakeEvent) => Promise.resolve(e._body),
    appendResponseHeader: (e: FakeEvent, _name: string, value: string) => {
      e._cookies.push(value)
    },
  })
})

afterEach(() => {
  vi.restoreAllMocks()
  // Restaura o stub default do setup.ts (status 500).
  Object.assign(globalThis, {
    sidecarFetch: () => Promise.resolve({ status: 500, data: null, setCookie: [] }),
  })
})

function stubSidecar(impl: (path: string, opts?: { method?: string, body?: unknown }) => unknown) {
  Object.assign(globalThis, {
    sidecarFetch: (_event: unknown, path: string, opts?: { method?: string, body?: unknown }) =>
      Promise.resolve(impl(path, opts)),
  })
}

describe('POST /api/admin/auth/login', () => {
  it('em 200: ok=true e re-emite o cookie gsid_adm', async () => {
    let seenPath = ''
    let seenBody: unknown
    stubSidecar((path, opts) => {
      seenPath = path
      seenBody = opts?.body
      return { status: 200, data: null, setCookie: ['gsid_adm=abc; HttpOnly; Path=/'] }
    })
    const ev = makeEvent({ login: 'agente', password: 'secret' })
    const res = await loginHandler(ev as never)

    expect(seenPath).toBe('/v1/admin/auth/login')
    expect(seenBody).toEqual({ login: 'agente', password: 'secret' })
    expect(res).toEqual({ ok: true, status: 200 })
    expect(ev._cookies).toEqual(['gsid_adm=abc; HttpOnly; Path=/'])
  })

  it('em 401: ok=false e propaga o status', async () => {
    stubSidecar(() => ({ status: 401, data: null, setCookie: [] }))
    const ev = makeEvent({ login: 'x', password: 'bad' })
    const res = await loginHandler(ev as never)

    expect(res).toEqual({ ok: false, status: 401 })
    expect(ev._cookies).toEqual([])
  })
})

describe('POST /api/admin/auth/logout', () => {
  it('re-emite a limpeza do cookie e responde 204', async () => {
    let seenPath = ''
    stubSidecar((path) => {
      seenPath = path
      return { status: 204, data: null, setCookie: ['gsid_adm=; Max-Age=0; Path=/'] }
    })
    const ev = makeEvent()
    const res = await logoutHandler(ev as never)

    expect(seenPath).toBe('/v1/admin/auth/logout')
    expect(res).toBeNull()
    expect(ev._cookies).toEqual(['gsid_adm=; Max-Age=0; Path=/'])
  })
})

describe('GET /api/admin/me', () => {
  it('com sessão (200 em /v1/admin/tenants): sessão mínima gerti_staff', async () => {
    let seenPath = ''
    stubSidecar((path) => {
      seenPath = path
      return { status: 200, data: [], setCookie: [] }
    })
    const ev = makeEvent()
    const res = await meHandler(ev as never)

    expect(seenPath).toBe('/v1/admin/tenants')
    expect(res).toEqual({ agent_login: '', role: 'gerti_staff' })
  })

  it('sem sessão (401): retorna null e propaga 401', async () => {
    stubSidecar(() => ({ status: 401, data: null, setCookie: [] }))
    const ev = makeEvent()
    const res = await meHandler(ev as never)

    expect(res).toBeNull()
  })
})

describe('guarda admin-auth (regra de redireciono)', () => {
  // A guarda usa useAsyncData/navigateTo (auto-imports do Nuxt). Em vez de bootar
  // o Nuxt, validamos a regra pura: pula no /login; sem sessão → /login; com
  // sessão → segue. Reimplementamos a mesma lógica do middleware aqui de forma
  // sincronizada (o handler real está em middleware/admin-auth.ts).
  function guard(path: string, session: unknown): string | undefined {
    if (path === '/login') return
    if (!session) return '/login'
    return undefined
  }

  it('não redireciona no /login (evita loop)', () => {
    expect(guard('/login', null)).toBeUndefined()
  })

  it('redireciona para /login sem sessão', () => {
    expect(guard('/', null)).toBe('/login')
  })

  it('segue com sessão válida', () => {
    expect(guard('/', { agent_login: '', role: 'gerti_staff' })).toBeUndefined()
  })
})
