// R16 — o "quadrinho" da operação: agentes, clientes, contratos. Proxy fino.
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/admin/licensing/overview')
  setResponseStatus(event, status)
  return data
})
