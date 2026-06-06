export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/tickets')
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
