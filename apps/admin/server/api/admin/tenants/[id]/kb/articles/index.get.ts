// Lista de artigos da Base de Conhecimento de um tenant (Spec #3, V1) — proxy
// fino. Repassa q/category/status/limit/offset. Contrato null=falha (a página
// distingue erro de vazio pelo array `items`).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const qp = getQuery(event)
  const search = new URLSearchParams()
  if (qp.q) search.set('q', String(qp.q))
  if (qp.category) search.set('category', String(qp.category))
  if (qp.status) search.set('status', String(qp.status))
  if (qp.limit) search.set('limit', String(qp.limit))
  if (qp.offset) search.set('offset', String(qp.offset))
  const qs = search.toString()
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/kb/articles${qs ? `?${qs}` : ''}`,
  )
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
