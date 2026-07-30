// Spec #3 · V1 — lista/busca de artigos da base de conhecimento (cliente).
// Repassa `q`/`category` opcionais; o sidecar já escopa `visibility=public` +
// `status=published` por sessão. GET → `null` em não-200 (contrato do portal).
export default defineEventHandler(async (event) => {
  const q = getQuery(event)
  const params = new URLSearchParams()
  if (q.q) params.set('q', String(q.q))
  if (q.category) params.set('category', String(q.category))
  const qs = params.toString()
  const { status, data } = await sidecarFetch(event, `/v1/kb/articles${qs ? `?${qs}` : ''}`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
