export default defineEventHandler(async (event) => {
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, '/v1/admin/checklists/templates', {
    method: 'POST',
    body,
  })
  setResponseStatus(event, status)
  return data
})
