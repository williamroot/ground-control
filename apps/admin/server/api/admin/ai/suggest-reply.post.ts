// Sugerir resposta (rascunho) com IA — proxy fino para o sidecar (#1N).
// Status passthrough (404 feature off; 503 indisponível). O rascunho NUNCA é
// enviado automaticamente — o agente edita e envia manualmente.
export default defineEventHandler(async (event) => {
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, '/v1/admin/ai/suggest-reply', {
    method: 'POST',
    body,
  })
  setResponseStatus(event, status)
  return data
})
