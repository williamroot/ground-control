// Busca federada do staff (Spec #3, V6) — proxy fino. `path` vem pronto em
// cada item devolvido pelo sidecar; NÃO concatenamos nada aqui nem na página.
export default defineEventHandler(async (event) => {
  const { q } = getQuery(event)
  const suffix = q ? `?q=${encodeURIComponent(String(q))}` : ''
  const { status, data } = await sidecarFetch(event, `/v1/admin/search${suffix}`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
