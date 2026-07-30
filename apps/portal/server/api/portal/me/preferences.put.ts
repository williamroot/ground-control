// #3 V3 — salva preferências (corpo parcial permitido). Propaga o status:
// 200 com o objeto atualizado, 422 quando algum valor cai fora do enum.
export default defineEventHandler(async (event) => {
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, '/v1/me/preferences', {
    method: 'PUT',
    body,
  })
  setResponseStatus(event, status)
  return data
})
