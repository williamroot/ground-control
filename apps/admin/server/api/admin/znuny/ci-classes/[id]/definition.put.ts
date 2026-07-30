// Grava nova versão da definição da classe de CI (Spec #4, Bloco B) — proxy
// fino. Propaga o status do sidecar: 200 sucesso, 422 quando o
// `DefinitionCheck` do Znuny reprova (o corpo traz `detail` com a mensagem —
// o operador precisa saber exatamente o que está errado antes de tentar de
// novo). Guard numérico no id -> 400 sem chamar o sidecar.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!isNumericId(id)) { setResponseStatus(event, 400); return null }
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/znuny/ci-classes/${id}/definition`,
    { method: 'PUT', body },
  )
  setResponseStatus(event, status)
  return data
})
