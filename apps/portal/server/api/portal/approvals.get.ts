// R7 — fila de aprovação do cliente. Proxy fino; o sidecar escopa por tenant
// (RLS) e o papel de quem decide é conferido lá, não aqui.
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/tickets/approvals')
  setResponseStatus(event, status)
  return data
})
