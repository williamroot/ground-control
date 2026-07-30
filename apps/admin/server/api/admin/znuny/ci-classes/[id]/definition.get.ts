// Definição (YAML) atual da classe de CI (Spec #4, Bloco B) — proxy fino.
// Guard numérico no id (mesmo padrão de faturas/tokens): malformado -> 400
// sem chamar o sidecar.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!isNumericId(id)) { setResponseStatus(event, 400); return null }
  const { status, data } = await sidecarFetch(event, `/v1/admin/znuny/ci-classes/${id}/definition`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
