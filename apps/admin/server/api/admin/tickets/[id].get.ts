// Detalhe de um ticket — proxy fino para o sidecar (#1J fase 3).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const { status, data } = await sidecarFetch(event, `/v1/admin/tickets/${id}`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
