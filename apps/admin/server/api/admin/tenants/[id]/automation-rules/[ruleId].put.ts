// Edita uma regra de automação (#1Q) — proxy fino. Propaga status (200/422/404).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const ruleId = getRouterParam(event, 'ruleId')
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/automation-rules/${ruleId}`,
    { method: 'PUT', body },
  )
  setResponseStatus(event, status)
  return data
})
