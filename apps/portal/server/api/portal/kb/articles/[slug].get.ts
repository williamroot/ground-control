// Spec #3 · V1 — detalhe de artigo por slug (cliente). O sidecar incrementa
// `views` nesta leitura e devolve 404 se o artigo não for público/publicado
// (ou não existir) — nunca 403 (anti-IDOR).
export default defineEventHandler(async (event) => {
  const slug = getRouterParam(event, 'slug')
  const { status, data } = await sidecarFetch(event, `/v1/kb/articles/${encodeURIComponent(slug ?? '')}`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
