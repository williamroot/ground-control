// PDF do relatório executivo (T-R18b.5) — passthrough binário.
//
// O sidecar devolve 503 quando o Znuny está fora: o PDF NÃO é gerado
// incompleto (aceite A18b.6). Aqui o status é repassado como veio, para a tela
// poder explicar o motivo em vez de baixar um arquivo quebrado.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!isTenantId(id)) { setResponseStatus(event, 404); return null }
  const month = String(getQuery(event).month ?? '')
  if (!isReportMonth(month)) { setResponseStatus(event, 422); return null }

  const { status, body, contentType } = await sidecarFetchRaw(
    event,
    `/v1/admin/tenants/${id}/reports/monthly.pdf?month=${encodeURIComponent(month)}`,
  )
  if (status !== 200) { setResponseStatus(event, status); return null }
  setResponseStatus(event, 200)
  setResponseHeader(event, 'content-type', contentType)
  setResponseHeader(event, 'content-disposition', `inline; filename="relatorio-${month}.pdf"`)
  return new Uint8Array(body)
})
