// Contratos que aceitam lançamento — alimenta o seletor da tela.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const { status, data } = await sidecarFetch(event, `/v1/admin/tenants/${id}/charges/contracts`)
  setResponseStatus(event, status)
  return data
})
