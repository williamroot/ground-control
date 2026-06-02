export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const q = getQuery(event)
  const page = Number(q.page ?? 1)
  const pageSize = Number(q.page_size ?? 50)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/contracts/${id}/consumption?page=${page}&page_size=${pageSize}`,
  )
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
