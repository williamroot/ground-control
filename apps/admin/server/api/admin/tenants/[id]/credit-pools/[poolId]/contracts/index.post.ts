export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const poolId = getRouterParam(event, 'poolId')
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/credit-pools/${poolId}/contracts`,
    { method: 'POST', body },
  )
  setResponseStatus(event, status)
  return data
})
