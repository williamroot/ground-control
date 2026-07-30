// Remove um item do Catálogo de Serviços (Spec #3, V2) — proxy fino. Propaga
// o status do sidecar (204 sucesso, 404 cross-tenant).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const itemId = getRouterParam(event, 'itemId')
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/catalog/items/${itemId}`,
    { method: 'DELETE' },
  )
  setResponseStatus(event, status)
  return data
})
