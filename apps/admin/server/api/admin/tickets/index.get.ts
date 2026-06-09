// Lista de tickets com busca opcional — proxy fino para o sidecar (#1J fase 3).
export default defineEventHandler(async (event) => {
  const qp = getQuery(event)
  const search = new URLSearchParams()
  if (qp.q) search.set('q', String(qp.q))
  if (qp.customer_id) search.set('customer_id', String(qp.customer_id))
  const path = '/v1/admin/tickets' + (search.toString() ? `?${search}` : '')
  const { status, data } = await sidecarFetch(event, path)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
