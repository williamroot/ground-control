export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!isTenantId(id)) { setResponseStatus(event, 404); return null }
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event, `/v1/admin/tenants/${id}/recurring-tasks`, { method: 'POST', body },
  )
  setResponseStatus(event, status)
  return data
})
