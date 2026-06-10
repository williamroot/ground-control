// Lista de regras de automação de um tenant (#1Q) — proxy fino.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/automation-rules`,
  )
  if (status !== 200) {
    setResponseStatus(event, status)
    return []
  }
  return data
})
