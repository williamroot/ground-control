// Inicia o checkout (proxy → sidecar POST /v1/checkout/sessions).
export default defineEventHandler(async (event) => {
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, '/v1/checkout/sessions', {
    method: 'POST',
    body,
  })
  setResponseStatus(event, status)
  return data
})
