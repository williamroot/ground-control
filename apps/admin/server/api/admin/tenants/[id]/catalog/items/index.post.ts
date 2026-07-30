// Cria um item do Catálogo de Serviços (Spec #3, V2) — proxy fino. Propaga o
// status do sidecar (201 sucesso, 404 tenant, 422 validação).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/catalog/items`,
    { method: 'POST', body },
  )
  setResponseStatus(event, status)
  return data
})
