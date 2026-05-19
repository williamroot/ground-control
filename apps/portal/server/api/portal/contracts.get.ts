export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/contracts')
  if (status !== 200) { setResponseStatus(event, status); return [] }
  return data
})
