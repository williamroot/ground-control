// Detalhe de um agente do Znuny (Spec #4, Bloco C) — proxy fino. Guard
// numérico no id -> 400 sem chamar o sidecar. Resposta nunca traz UserPw.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!isNumericId(id)) { setResponseStatus(event, 400); return null }
  const { status, data } = await sidecarFetch(event, `/v1/admin/znuny/agents/${id}`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
