export default defineEventHandler(async (event) => {
  const contentType = getRequestHeader(event, 'content-type') || ''
  const raw = await readRawBody(event, false) as Uint8Array
  const { status, data } = await sidecarFetch(event, '/v1/tickets', {
    method: 'POST',
    rawBody: raw,
    contentType,
  })
  setResponseStatus(event, status)
  return data
})
