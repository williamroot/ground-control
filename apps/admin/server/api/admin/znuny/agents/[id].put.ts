// Edita um agente do Znuny (Spec #4, Bloco C) — proxy fino, compartilhado por
// duas ações DISTINTAS da tela: salvar cadastro (UserFirstname/UserLastname/
// UserEmail/ValidID) e definir senha (NewPassword). A separação é garantida
// pelo composable (payloads nunca se misturam) — este proxy só encaminha o
// corpo como veio. Guard numérico no id -> 400 sem chamar o sidecar.
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
