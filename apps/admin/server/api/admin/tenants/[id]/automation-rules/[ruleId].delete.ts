// Remove uma regra de automação (#1Q) — proxy fino. Propaga status (204/404).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const ruleId = getRouterParam(event, 'ruleId')
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/automation-rules/${ruleId}`,
    { method: 'DELETE' },
  )
  setResponseStatus(event, status)
  return data
})
