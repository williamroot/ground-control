// Lista dispositivos do agente de inventário (#1R-a) — proxy fino.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const { status, data } = await sidecarFetch(event, `/v1/admin/tenants/${id}/devices`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
