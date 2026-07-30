// Spec #3 · V2 — item completo do catálogo (usado para pré-preencher a
// abertura de chamado). Guard de formato (uuid) → 400, nunca deixa passar um
// path param malformado pro sidecar. Item cross-tenant/inativo → 404.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!/^[0-9a-fA-F-]{36}$/.test(id ?? '')) { setResponseStatus(event, 400); return null }
  const { status, data } = await sidecarFetch(event, `/v1/catalog/items/${id}`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
