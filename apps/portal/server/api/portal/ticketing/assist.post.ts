// #1S — proxy do assistente de escrita. Repassa {title?, body} ao sidecar e
// devolve {title, body} + o status AS-IS (404 feature off, 429 rate-limit,
// 503 IA fora) para a UI tratar. Server-side: o browser nunca fala com o sidecar.
export default defineEventHandler(async (event) => {
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, '/v1/ticketing/assist', {
    method: 'POST',
    body,
  })
  setResponseStatus(event, status)
  return data
})
