// Edita uma regra de domínio (T-R9.5) — proxy fino.
// `name` é interpolado no path do sidecar: guard antes de qualquer chamada.
export default defineEventHandler(async (event) => {
  const name = getRouterParam(event, 'name')
  if (!isFilterName(name)) { setResponseStatus(event, 404); return null }
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/znuny/postmaster-filters/${encodeURIComponent(name as string)}`,
    { method: 'PUT', body },
  )
  setResponseStatus(event, status)
  return data
})
