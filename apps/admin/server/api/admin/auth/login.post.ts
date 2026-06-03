// Login de agente Gerti (Spec #1G-a, T1.E). Proxy server-side para o sidecar:
// repassa {login, password}, re-emite o cookie de sessão `gsid_adm` como
// first-party e propaga o status (401 credenciais / 503 sidecar fora).
export default defineEventHandler(async (event) => {
  const body = await readBody<{ login: string, password: string }>(event)
  const { status, setCookie } = await sidecarFetch<unknown>(
    event,
    '/v1/admin/auth/login',
    { method: 'POST', body },
  )
  // Re-emite o cookie `gsid_adm` do sidecar como first-party do host admin.
  for (const c of setCookie) appendResponseHeader(event, 'set-cookie', c)
  if (status !== 200) {
    setResponseStatus(event, status)
    return { ok: false, status }
  }
  return { ok: true, status }
})
