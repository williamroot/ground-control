// Logout de agente Gerti (Spec #1G-a, T1.E). Encaminha ao sidecar e re-emite o
// cookie de limpeza do `gsid_adm`; responde 204.
export default defineEventHandler(async (event) => {
  const { setCookie } = await sidecarFetch<unknown>(
    event,
    '/v1/admin/auth/logout',
    { method: 'POST' },
  )
  for (const c of setCookie) appendResponseHeader(event, 'set-cookie', c)
  setResponseStatus(event, 204)
  return null
})
