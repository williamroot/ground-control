// Troca os grupos/papéis de um agente do Znuny (Spec #4, Bloco C) — proxy
// fino. Ação mais perigosa da spec: o sidecar audita antes/depois e recusa
// (422) um agente removendo a si mesmo do grupo `admin` (anti-lockout). Guard
// numérico no id -> 400 sem chamar o sidecar.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!isNumericId(id)) { setResponseStatus(event, 400); return null }
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, `/v1/admin/znuny/agents/${id}/groups`, {
    method: 'PUT',
    body,
  })
  setResponseStatus(event, status)
  return data
})
