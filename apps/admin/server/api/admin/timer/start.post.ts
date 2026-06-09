// Inicia um timer para um ticket — proxy fino para o sidecar (#1J fase 3).
export default defineEventHandler(async (event) => {
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, '/v1/admin/timer/start', { method: 'POST', body })
  setResponseStatus(event, status)
  return data
})
