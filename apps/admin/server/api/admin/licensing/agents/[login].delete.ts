export default defineEventHandler(async (event) => {
  const login = getRouterParam(event, 'login')
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/licensing/agents/${encodeURIComponent(login ?? '')}`,
    { method: 'DELETE' },
  )
  setResponseStatus(event, status)
  return data
})
