// Edita um item do Catálogo de Serviços (Spec #3, V2) — proxy fino. Propaga o
// status do sidecar (200 sucesso, 404 cross-tenant, 422 validação).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const itemId = getRouterParam(event, 'itemId')
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/catalog/items/${itemId}`,
    { method: 'PUT', body },
  )
  setResponseStatus(event, status)
  return data
})
