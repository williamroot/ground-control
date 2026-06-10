// Gera um token de instalação (#1R-a) — proxy fino. Retorna o token EM CLARO uma
// única vez + o comando de instalação. Propaga o status do sidecar (201/404/422).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/agent-tokens`,
    { method: 'POST', body },
  )
  setResponseStatus(event, status)
  return data
})
