export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const itemId = getRouterParam(event, 'itemId')
  if (!/^[0-9]+$/.test(id ?? '')) { setResponseStatus(event, 400); return null }
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tickets/${id}/checklist-items/${itemId}`,
    { method: 'PUT', body },
  )
  setResponseStatus(event, status)
  return data
})
