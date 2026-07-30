// Detalhe de um item do catálogo — proxy fino (Spec #3, V2). Usado para
// pré-preencher o formulário de edição no console.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const itemId = getRouterParam(event, 'itemId')
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/catalog/items/${itemId}`,
  )
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
