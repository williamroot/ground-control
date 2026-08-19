export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const taskId = getRouterParam(event, 'taskId')
  if (!isTenantId(id) || !isTenantId(taskId)) { setResponseStatus(event, 404); return null }
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event, `/v1/admin/tenants/${id}/recurring-tasks/${taskId}`, { method: 'PUT', body },
  )
  setResponseStatus(event, status)
  return data
})
