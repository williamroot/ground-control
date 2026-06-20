// Lista de planos públicos (proxy → sidecar /v1/checkout/plans).
export default defineEventHandler(async (event) => {
  const q = getQuery(event)
  const query = q.audience ? { audience: String(q.audience) } : undefined
  const { status, data } = await sidecarFetch(event, '/v1/checkout/plans', { query })
  if (status !== 200) { setResponseStatus(event, status); return [] }
  return data
})
