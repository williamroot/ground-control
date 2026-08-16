// Pessoas do cliente, lendo o Znuny como fonte de verdade (T-R2.2) — proxy fino.
// A resposta traz `degraded: true` quando o Znuny está fora; a tela precisa
// dizer isso, senão uma lista curta parece exclusão.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!isTenantId(id)) { setResponseStatus(event, 404); return null }
  const { status, data } = await sidecarFetch(event, `/v1/admin/tenants/${id}/users`)
  setResponseStatus(event, status)
  return data
})
