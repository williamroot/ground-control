export default defineEventHandler(async (event) => {
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, '/v1/admin/licensing/agents', {
    method: 'PUT',
    body,
  })
  setResponseStatus(event, status)
  return data
})
