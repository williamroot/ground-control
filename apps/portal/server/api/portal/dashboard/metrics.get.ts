// Indicadores do dashboard (#1O) — proxy fino p/ o sidecar (admin do tenant,
// tenant-scoped). Repassa o status; aceita ?period=30d|90d.
export default defineEventHandler(async (event) => {
  const qp = getQuery(event)
  const period = qp.period ? `?period=${encodeURIComponent(String(qp.period))}` : ''
  const { status, data } = await sidecarFetch(event, `/v1/dashboard/metrics${period}`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
