// Lista tokens de instalação do agente (#1R-a) — proxy fino. Sem plaintext.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const { status, data } = await sidecarFetch(event, `/v1/admin/tenants/${id}/agent-tokens`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
