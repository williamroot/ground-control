// Cria uma regra de domínio (T-R9.5) — proxy fino.
export default defineEventHandler(async (event) => {
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    '/v1/admin/znuny/postmaster-filters',
    { method: 'POST', body },
  )
  setResponseStatus(event, status)
  return data
})
