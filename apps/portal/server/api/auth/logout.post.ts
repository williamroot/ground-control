export default defineEventHandler(async (event) => {
  const { status, setCookie } = await sidecarFetch<unknown>(
    event,
    '/v1/auth/logout',
    { method: 'POST' },
  )
  for (const c of setCookie) appendResponseHeader(event, 'set-cookie', c)
  setResponseStatus(event, status === 204 ? 204 : status)
  return null
})
