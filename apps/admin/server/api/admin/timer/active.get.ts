// Timer ativo do agente autenticado — proxy fino para o sidecar (#1J fase 3).
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/admin/timer/active')
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
