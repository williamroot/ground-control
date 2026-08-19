// T-R15.3 — lançamentos avulsos do cliente.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const q = getQuery(event)
  const qs = q.contract_id ? `?contract_id=${encodeURIComponent(String(q.contract_id))}` : ''
  const { status, data } = await sidecarFetch(event, `/v1/admin/tenants/${id}/charges${qs}`)
  setResponseStatus(event, status)
  return data
})
