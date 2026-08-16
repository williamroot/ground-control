// Relatório executivo do mês em JSON (T-R18b.5) — proxy fino.
// Mês inválido morre aqui, sem chamar o sidecar (o sidecar também recusa; isto
// é defesa em profundidade e um round-trip a menos para o operador).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!isTenantId(id)) { setResponseStatus(event, 404); return null }
  const month = String(getQuery(event).month ?? '')
  if (!isReportMonth(month)) { setResponseStatus(event, 422); return { detail: 'mês inválido' } }
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/reports/monthly?month=${encodeURIComponent(month)}`,
  )
  setResponseStatus(event, status)
  return data
})
