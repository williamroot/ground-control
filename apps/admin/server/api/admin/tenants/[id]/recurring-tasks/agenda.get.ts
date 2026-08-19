// Agenda dos próximos N dias (T-R11.5) — a visão que o técnico usa.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!isTenantId(id)) { setResponseStatus(event, 404); return null }
  const days = Number(getQuery(event).days ?? 30)
  const safe = Number.isInteger(days) && days >= 1 && days <= 180 ? days : 30
  const { status, data } = await sidecarFetch(
    event, `/v1/admin/tenants/${id}/recurring-tasks/agenda?days=${safe}`,
  )
  setResponseStatus(event, status)
  return data
})
