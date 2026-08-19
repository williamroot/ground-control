// Checklists aplicados a um chamado. Guard numérico no id (anti path-injection).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!/^[0-9]+$/.test(id ?? '')) { setResponseStatus(event, 400); return null }
  const { status, data } = await sidecarFetch(event, `/v1/admin/tickets/${id}/checklists`)
  setResponseStatus(event, status)
  return data
})
