// Corrige o cadastro de um cliente (T-R1.2) — proxy fino. Propaga o status do
// sidecar (200/404/422) e o corpo, para a tela mostrar o `detail` em português
// (o 422 nomeia o campo imutável que alguém tentou mudar).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!isTenantId(id)) { setResponseStatus(event, 404); return null }
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}`,
    { method: 'PUT', body },
  )
  setResponseStatus(event, status)
  return data
})
