// R6 — configuração de faturamento do cliente. Proxy fino.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const { status, data } = await sidecarFetch(event, `/v1/admin/tenants/${id}/billing-config`)
  setResponseStatus(event, status)
  return data
})
