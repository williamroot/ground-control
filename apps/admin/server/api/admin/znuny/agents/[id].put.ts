// Edita o cadastro de um agente do Znuny (Spec #4, Bloco C) — proxy fino.
// Só cadastro (UserFirstname/UserLastname/UserEmail/ValidID) — NUNCA senha.
// Definir senha é uma rota separada e explícita:
// POST /api/admin/znuny/agents/{id}/password (correção pós-revisão
// adversarial: o endpoint antigo, PUT com `NewPassword`, nunca existiu de
// verdade no backend). Guard numérico no id -> 400 sem chamar o sidecar.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!isNumericId(id)) { setResponseStatus(event, 400); return null }
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, `/v1/admin/znuny/agents/${id}`, {
    method: 'PUT',
    body,
  })
  setResponseStatus(event, status)
  return data
})
