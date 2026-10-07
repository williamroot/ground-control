import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  LOGIN_MSG_GENERIC,
  LOGIN_MSG_INVALID,
  LOGIN_MSG_UNAVAILABLE,
  loginErrorMessage,
  loginStatusFromError,
} from '../shared/login-error'

// T3 / C2 — o login distinguia nada: senha errada e queda davam a mesma frase.
// O cliente digitou a senha errada e não soube se era senha ou indisponibilidade.

describe('loginErrorMessage: status → mensagem', () => {
  it.each([401])('%i → usuário ou senha incorretos', (s) => {
    expect(loginErrorMessage(s)).toBe(LOGIN_MSG_INVALID)
  })

  it('403 (WAF/Cloudflare, nunca o sidecar) → genérica, não "senha incorreta"', () => {
    expect(loginErrorMessage(403)).toBe(LOGIN_MSG_GENERIC)
  })

  it.each([500, 502, 503, 504, 599, 408])('%i → serviço indisponível', (s) => {
    expect(loginErrorMessage(s)).toBe(LOGIN_MSG_UNAVAILABLE)
  })

  it.each([undefined, null, 0])('sem status (%s: rede/timeout) → serviço indisponível', (s) => {
    expect(loginErrorMessage(s)).toBe(LOGIN_MSG_UNAVAILABLE)
  })

  it.each([400, 404, 422, 429])('%i → mensagem genérica', (s) => {
    expect(loginErrorMessage(s)).toBe(LOGIN_MSG_GENERIC)
  })

  it('textos em pt-BR exatos', () => {
    expect(LOGIN_MSG_INVALID).toBe('Usuário ou senha incorretos.')
    expect(LOGIN_MSG_UNAVAILABLE).toBe('Serviço indisponível no momento. Tente de novo em instantes.')
  })
})

describe('loginStatusFromError: status de um erro do $fetch', () => {
  it('lê response.status (FetchError do ofetch)', () => {
    expect(loginStatusFromError({ response: { status: 401 }, status: 401 })).toBe(401)
  })
  it('lê statusCode quando só ele existe', () => {
    expect(loginStatusFromError({ statusCode: 503 })).toBe(503)
  })
  it('cai para o corpo do proxy ({ ok:false, status })', () => {
    expect(loginStatusFromError({ data: { ok: false, status: 403 } })).toBe(403)
  })
  it('erro de rede/timeout (sem resposta) → undefined', () => {
    expect(loginStatusFromError(new TypeError('fetch failed'))).toBeUndefined()
    expect(loginStatusFromError({ name: 'TimeoutError' })).toBeUndefined()
    expect(loginStatusFromError(null)).toBeUndefined()
    expect(loginStatusFromError('x')).toBeUndefined()
  })
  it('ponta a ponta: erro de rede vira "indisponível", 401 vira "incorretos"', () => {
    expect(loginErrorMessage(loginStatusFromError(new TypeError('fetch failed')))).toBe(LOGIN_MSG_UNAVAILABLE)
    expect(loginErrorMessage(loginStatusFromError({ response: { status: 401 } }))).toBe(LOGIN_MSG_INVALID)
  })
})

describe('POST /api/auth/login (proxy)', () => {
  afterEach(() => vi.unstubAllGlobals())

  // `setResponseStatus` é stubado só para o módulo carregar (o h3 o
  // auto-importa no transform); o contrato observável é o corpo { ok, status },
  // que é o que a página de login lê — mesmo harness de preferences-proxy.
  async function run(fetchImpl: ReturnType<typeof vi.fn>) {
    const setStatus = vi.fn()
    vi.stubGlobal('defineEventHandler', (fn: (e: unknown) => unknown) => fn)
    vi.stubGlobal('readBody', vi.fn().mockResolvedValue({ username: 'eduardo.salvi', password: 'x' }))
    vi.stubGlobal('setResponseStatus', setStatus)
    vi.stubGlobal('appendResponseHeader', vi.fn())
    vi.stubGlobal('sidecarFetch', fetchImpl)
    const mod = await import('../server/api/auth/login.post')
    const handler = mod.default as unknown as (e: unknown) => Promise<unknown>
    const out = await handler({})
    return { out, mod }
  }

  it('200 → ok e usa timeout na chamada ao sidecar', async () => {
    const f = vi.fn().mockResolvedValue({ status: 200, data: { status: 'ok' }, setCookie: [] })
    const { out, mod } = await run(f)
    expect(out).toEqual({ ok: true, data: { status: 'ok' } })
    expect(f).toHaveBeenCalledWith({}, '/v1/auth/login', {
      method: 'POST',
      body: { username: 'eduardo.salvi', password: 'x' },
      timeoutMs: mod.LOGIN_SIDECAR_TIMEOUT_MS,
    })
  })

  it('401 do sidecar é repassado como 401', async () => {
    const { out } = await run(vi.fn().mockResolvedValue({ status: 401, data: null, setCookie: [] }))
    expect(out).toEqual({ ok: false, status: 401 })
  })

  it('503 do sidecar (Znuny fora) é repassado como 503', async () => {
    const { out } = await run(vi.fn().mockResolvedValue({ status: 503, data: null, setCookie: [] }))
    expect(out).toEqual({ ok: false, status: 503 })
  })

  it('conexão recusada → 503, nunca 401', async () => {
    const { out } = await run(vi.fn().mockRejectedValue(new TypeError('fetch failed')))
    expect(out).toEqual({ ok: false, status: 503 })
  })

  it('timeout do sidecar → 503, nunca 401', async () => {
    const err = new DOMException('The operation was aborted due to timeout', 'TimeoutError')
    const { out } = await run(vi.fn().mockRejectedValue(err))
    expect(out).toEqual({ ok: false, status: 503 })
  })
})
