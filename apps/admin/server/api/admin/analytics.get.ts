// Analytics do console (#1O) — proxy fino p/ o sidecar (cross-tenant, agente).
// Repassa o status; exige tenant_id; aceita ?period=30d|90d.
export default defineEventHandler(async (event) => {
  const qp = getQuery(event)
  const search = new URLSearchParams()
  if (qp.tenant_id) search.set('tenant_id', String(qp.tenant_id))
  if (qp.period) search.set('period', String(qp.period))
  const path = `/v1/admin/analytics${search.toString() ? `?${search}` : ''}`
  const { status, data } = await sidecarFetch(event, path)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
