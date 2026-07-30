// #3 V3 — preferências do usuário logado. O sidecar cria com defaults na
// primeira leitura (upsert idempotente) — nunca 404 para uma sessão válida.
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/me/preferences')
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
