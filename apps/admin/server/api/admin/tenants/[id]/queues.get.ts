// Filas associadas ao cliente, com o grupo que atende cada uma (T-R5.4) — proxy fino.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!isTenantId(id)) { setResponseStatus(event, 404); return null }
  const { status, data } = await sidecarFetch(event, `/v1/admin/tenants/${id}/queues`)
  setResponseStatus(event, status)
  return data
})
