export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, `/v1/admin/tenants/${id}/billing-config`, {
    method: 'PUT',
    body,
  })
  setResponseStatus(event, status)
  return data
})
