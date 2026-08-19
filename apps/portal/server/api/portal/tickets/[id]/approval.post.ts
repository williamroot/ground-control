// R7 — decisão de aprovação. Guard de id numérico (anti path-injection), como
// em reply/csat. O 403 de "você não é aprovador" vem do sidecar.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!/^[0-9]+$/.test(id ?? '')) { setResponseStatus(event, 400); return null }
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, `/v1/tickets/${id}/approval`, {
    method: 'POST',
    body,
  })
  setResponseStatus(event, status)
  return data
})
