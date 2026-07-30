// #3 V6 — busca federada do cliente (chamados/ativos/KB/catálogo). `q`
// obrigatório 2-100 chars — validação de verdade é o 422 do sidecar; aqui só
// repassamos.
export default defineEventHandler(async (event) => {
  const q = getQuery(event)
  const query = typeof q.q === 'string' ? q.q : ''
  const { status, data } = await sidecarFetch(event, `/v1/search?q=${encodeURIComponent(query)}`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
