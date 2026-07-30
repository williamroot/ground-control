// Spec #3 · V2 — vitrine do catálogo de serviços (cliente). O sidecar já
// escopa `active=true` e ordena por `sort_order,name`. `category` é opcional.
export default defineEventHandler(async (event) => {
  const q = getQuery(event)
  const category = q.category ? `?category=${encodeURIComponent(String(q.category))}` : ''
  const { status, data } = await sidecarFetch(event, `/v1/catalog/items${category}`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
