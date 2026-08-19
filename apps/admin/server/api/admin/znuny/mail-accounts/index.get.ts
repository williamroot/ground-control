// Contas de recebimento (T-R9.7) — proxy fino. A resposta do sidecar nunca
// carrega senha; este proxy não acrescenta nada que possa carregar.
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/admin/znuny/mail-accounts')
  setResponseStatus(event, status)
  return data
})
