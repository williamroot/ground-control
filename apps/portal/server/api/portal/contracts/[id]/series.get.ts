export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const q = getQuery(event)
  const granularity = q.granularity === 'week' ? 'week' : 'day'
  const { status, data } = await sidecarFetch(
    event,
    `/v1/contracts/${id}/series?granularity=${granularity}`,
  )
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
