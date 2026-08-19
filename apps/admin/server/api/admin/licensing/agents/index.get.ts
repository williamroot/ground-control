export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/admin/licensing/agents')
  setResponseStatus(event, status)
  return data
})
