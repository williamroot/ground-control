// R13b — modelos de checklist (procedimento da Gerti, global).
export default defineEventHandler(async (event) => {
  const q = getQuery(event)
  const qs = q.include_inactive ? '?include_inactive=true' : ''
  const { status, data } = await sidecarFetch(event, `/v1/admin/checklists/templates${qs}`)
  setResponseStatus(event, status)
  return data
})
