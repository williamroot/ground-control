// Cadastra uma pessoa do cliente (T-R2.1) — proxy fino. É o MESMO cadastro que
// serve portal e e-mail (o diferencial do R2). A senha vai no corpo e nunca é
// registrada em log aqui.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!isTenantId(id)) { setResponseStatus(event, 404); return null }
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/users`,
    { method: 'POST', body },
  )
  setResponseStatus(event, status)
  return data
})
