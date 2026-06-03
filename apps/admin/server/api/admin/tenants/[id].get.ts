// Detalhe de um cliente (branding, usuários, contratos) — proxy fino (#1G-a T1.F).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const { status, data } = await sidecarFetch(event, `/v1/admin/tenants/${id}`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
