export default defineEventHandler(async (event) => {
  const body = await readBody<{ username: string, password: string }>(event)
  const { status, data, setCookie } = await sidecarFetch<{ status: string }>(
    event,
    '/v1/auth/login',
    { method: 'POST', body },
  )
  // Re-emit the sidecar gsid cookie as first-party for the subdomain (H8).
  for (const c of setCookie) appendResponseHeader(event, 'set-cookie', c)
  if (status !== 200) {
    setResponseStatus(event, status)
    return { ok: false, status }
  }
  return { ok: true, data }
})
