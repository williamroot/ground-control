// Define a senha de um agente do Znuny (Spec #4, Bloco C — correção
// pós-revisão adversarial) — proxy fino. Operação SEPARADA de PUT
// /agents/{id}: o endpoint antigo (PUT com `NewPassword`) nunca existiu de
// verdade no backend, o botão "Definir senha" sempre respondia 422. Guard
// numérico no id -> 400 sem chamar o sidecar.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!isNumericId(id)) { setResponseStatus(event, 400); return null }
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, `/v1/admin/znuny/agents/${id}/password`, {
    method: 'POST',
    body,
  })
  setResponseStatus(event, status)
  return data
})
