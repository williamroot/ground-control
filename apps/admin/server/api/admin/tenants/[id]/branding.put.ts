// Salva a identidade visual do tenant (Spec #3, V4) — proxy fino. Propaga o
// status do sidecar (200/404/422) e o corpo (inclui o detail do 422 para a
// página traduzir campo a campo).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/branding`,
    { method: 'PUT', body },
  )
  setResponseStatus(event, status)
  return data
})
