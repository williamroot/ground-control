// #3 V3 — lista de notificações do usuário logado (status=all|unread|read,
// paginação limit/offset). Repassa a query como veio; o sidecar valida.
export default defineEventHandler(async (event) => {
  const q = getQuery(event)
  const params = new URLSearchParams()
  if (q.status) params.set('status', String(q.status))
  if (q.limit) params.set('limit', String(q.limit))
  if (q.offset) params.set('offset', String(q.offset))
  const qs = params.toString()
  const { status, data } = await sidecarFetch(event, `/v1/notifications${qs ? `?${qs}` : ''}`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
