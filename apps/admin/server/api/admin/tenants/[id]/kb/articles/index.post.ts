// Cria um artigo da Base de Conhecimento (Spec #3, V1) — proxy fino. Propaga
// o status do sidecar (201 sucesso, 404 tenant, 422 validação).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/kb/articles`,
    { method: 'POST', body },
  )
  setResponseStatus(event, status)
  return data
})
