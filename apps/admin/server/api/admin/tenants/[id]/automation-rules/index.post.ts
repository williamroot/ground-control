// Cria uma regra de automação (#1Q) — proxy fino. Propaga status (201/422/404).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/automation-rules`,
    { method: 'POST', body },
  )
  setResponseStatus(event, status)
  return data
})
