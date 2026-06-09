export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!/^[0-9]+$/.test(id ?? '')) { setResponseStatus(event, 400); return null }
  const { status, data } = await sidecarFetch(event, `/v1/tickets/${id}`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
