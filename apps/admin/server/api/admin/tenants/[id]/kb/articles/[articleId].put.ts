// Edita um artigo da Base de Conhecimento (Spec #3, V1) — proxy fino. Propaga
// o status do sidecar (200 sucesso, 404 cross-tenant, 422 validação).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const articleId = getRouterParam(event, 'articleId')
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/kb/articles/${articleId}`,
    { method: 'PUT', body },
  )
  setResponseStatus(event, status)
  return data
})
