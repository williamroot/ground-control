// Mapeamento status → mensagem do login do portal (T3 / C2).
//
// Por que existe: o login mostrava "Credenciais inválidas ou serviço
// indisponível." para QUALQUER falha. Um cliente com a senha errada não sabia
// se o problema era a senha ou uma queda. Aqui separamos os dois casos:
//
// - 401/403                       → a credencial foi recusada.
// - 5xx, 408, timeout, rede caída → o serviço não respondeu (`status` ausente).
// - qualquer outro status          → mensagem genérica (não dá para afirmar).
//
// Função pura e sem Nuxt: testável em vitest e usada por `pages/login.vue`.

export const LOGIN_MSG_INVALID = 'Usuário ou senha incorretos.'
export const LOGIN_MSG_UNAVAILABLE = 'Serviço indisponível no momento. Tente de novo em instantes.'
export const LOGIN_MSG_GENERIC = 'Credenciais inválidas ou serviço indisponível.'

/**
 * `status` ausente (null/undefined/0) significa que não houve resposta HTTP:
 * erro de rede, conexão recusada ou timeout — tratado como indisponível.
 */
export function loginErrorMessage(status: number | null | undefined): string {
  if (!status) return LOGIN_MSG_UNAVAILABLE
  // Só 401: o login do sidecar nunca devolve 403 — um 403 vem de WAF/Cloudflare
  // na frente do portal, e dizer "senha incorreta" mandaria trocar senha certa.
  if (status === 401) return LOGIN_MSG_INVALID
  if (status === 408 || status >= 500) return LOGIN_MSG_UNAVAILABLE
  return LOGIN_MSG_GENERIC
}

/**
 * Extrai o status HTTP de um erro do `$fetch` (ofetch `FetchError`). Sem
 * resposta (rede/timeout/abort) devolve `undefined`.
 */
export function loginStatusFromError(err: unknown): number | undefined {
  if (!err || typeof err !== 'object') return undefined
  const e = err as {
    status?: unknown
    statusCode?: unknown
    response?: { status?: unknown }
    data?: { status?: unknown }
  }
  for (const s of [e.response?.status, e.status, e.statusCode, e.data?.status]) {
    if (typeof s === 'number' && s > 0) return s
  }
  return undefined
}
