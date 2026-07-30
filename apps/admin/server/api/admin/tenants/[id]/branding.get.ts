// Identidade visual do tenant (Spec #3, V4) — proxy fino. Propaga status
// (200/404); null quando não-200 (contrato "null = falha" das páginas admin).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const { status, data } = await sidecarFetch(event, `/v1/admin/tenants/${id}/branding`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
