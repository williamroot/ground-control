// T-R3.2 — bolsas de crédito compartilhadas do cliente, com saldo do grupo.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const { status, data } = await sidecarFetch(event, `/v1/admin/tenants/${id}/credit-pools`)
  setResponseStatus(event, status)
  return data
})
