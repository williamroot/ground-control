// Remove um artigo da Base de Conhecimento (Spec #3, V1) — proxy fino. Propaga
// o status do sidecar (204 sucesso, 404 cross-tenant).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const articleId = getRouterParam(event, 'articleId')
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/kb/articles/${articleId}`,
    { method: 'DELETE' },
  )
  setResponseStatus(event, status)
  return data
})
