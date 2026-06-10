// Gera fatura a partir de um ciclo — proxy fino (#1P). Propaga o status do
// sidecar (201 sucesso, 404 tenant/ciclo inexistente, 409 já faturado/ciclo aberto).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/invoices`,
    { method: 'POST', body },
  )
  setResponseStatus(event, status)
  return data
})
