// Consumo do cliente para o gráfico do console (T-R18a.3) — proxy fino.
// `window`/`count` são repassados: a tela oferece o seletor mês↔ciclo, que é
// como a suposição S3 vira escolha do operador em vez de aposta nossa.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!isTenantId(id)) { setResponseStatus(event, 404); return null }
  const q = getQuery(event)
  const params = new URLSearchParams()
  if (q.window === 'months' || q.window === 'cycles') params.set('window', String(q.window))
  const count = Number(q.count)
  if (Number.isInteger(count) && count >= 1 && count <= 24) params.set('count', String(count))
  const qs = params.toString()
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/consumption-series${qs ? `?${qs}` : ''}`,
  )
  setResponseStatus(event, status)
  return data
})
