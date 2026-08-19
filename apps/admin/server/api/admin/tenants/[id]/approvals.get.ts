// R7 — fila de aprovação vista pelo console (a Gerti acompanha o que trava).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const { status, data } = await sidecarFetch(event, `/v1/admin/tenants/${id}/approvals`)
  setResponseStatus(event, status)
  return data
})
