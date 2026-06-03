// Lista de clientes (cross-tenant) — proxy fino p/ o sidecar (#1G-a T1.F).
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/admin/tenants')
  if (status !== 200) { setResponseStatus(event, status); return [] }
  return data
})
