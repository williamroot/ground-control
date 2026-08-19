// Cadastra uma caixa de recebimento (T-R9.4/T-R9.7) — proxy fino.
// A senha vai no corpo e NUNCA é registrada em log aqui.
export default defineEventHandler(async (event) => {
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    '/v1/admin/znuny/mail-accounts',
    { method: 'POST', body },
  )
  setResponseStatus(event, status)
  return data
})
