export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/ticketing/contracts')
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
