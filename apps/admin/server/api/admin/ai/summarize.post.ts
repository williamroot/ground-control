// Resumir um chamado com IA — proxy fino para o sidecar (#1N). Status passthrough
// (404 quando a feature está off; 503 quando o Ollama/Znuny está indisponível).
export default defineEventHandler(async (event) => {
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, '/v1/admin/ai/summarize', {
    method: 'POST',
    body,
  })
  setResponseStatus(event, status)
  return data
})
