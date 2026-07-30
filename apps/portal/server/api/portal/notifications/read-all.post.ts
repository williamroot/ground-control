// #3 V3 — marca todas as notificações do usuário logado como lidas.
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/notifications/read-all', {
    method: 'POST',
  })
  setResponseStatus(event, status)
  return data
})
