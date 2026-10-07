// Timeout da chamada ao sidecar no login. O sidecar já devolve 503 quando o
// Znuny cai; isto cobre o caso do PRÓPRIO sidecar não responder.
export const LOGIN_SIDECAR_TIMEOUT_MS = 10_000

export default defineEventHandler(async (event) => {
  const body = await readBody<{ username: string, password: string }>(event)
  let result: { status: number, data: { status: string } | null, setCookie: string[] }
  try {
    result = await sidecarFetch<{ status: string }>(
      event,
      '/v1/auth/login',
      { method: 'POST', body, timeoutMs: LOGIN_SIDECAR_TIMEOUT_MS },
    )
  }
  catch {
    // Conexão recusada, DNS, reset ou timeout: o sidecar NÃO respondeu. Isso é
    // indisponibilidade (503), nunca "credencial inválida" (401) — senão a
    // página de login diria "senha incorreta" durante uma queda (T3 / C2).
    setResponseStatus(event, 503)
    return { ok: false, status: 503 }
  }
  const { status, data, setCookie } = result
  // Re-emit the sidecar gsid cookie as first-party for the subdomain (H8).
  for (const c of setCookie) appendResponseHeader(event, 'set-cookie', c)
  if (status !== 200) {
    setResponseStatus(event, status)
    return { ok: false, status }
  }
  return { ok: true, data }
})
