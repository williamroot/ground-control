// Status da sessão de checkout (polling). Proxy → GET /v1/checkout/sessions/{id}?token=
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const token = String(getQuery(event).token || '')
  const { status, data } = await sidecarFetch(event, `/v1/checkout/sessions/${id}`, {
    query: { token },
  })
  setResponseStatus(event, status)
  return data
})
