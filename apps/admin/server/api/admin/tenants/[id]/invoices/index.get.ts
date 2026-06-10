// Lista de faturas de um cliente — proxy fino (#1P).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const { status, data } = await sidecarFetch(event, `/v1/admin/tenants/${id}/invoices`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
