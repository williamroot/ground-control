// Lista de itens do Catálogo de Serviços de um tenant (Spec #3, V2) — proxy
// fino, ordenado por sort_order no sidecar. Contrato null=falha.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const qp = getQuery(event)
  const search = new URLSearchParams()
  if (qp.category) search.set('category', String(qp.category))
  const qs = search.toString()
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/catalog/items${qs ? `?${qs}` : ''}`,
  )
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
