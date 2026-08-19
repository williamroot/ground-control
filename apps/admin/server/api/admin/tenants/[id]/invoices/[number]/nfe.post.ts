// T-R15.5 — nfe da fatura no Asaas. Guard numérico no number, como em paid/void.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const number = getRouterParam(event, 'number')
  if (!/^[0-9]+$/.test(number ?? '')) { setResponseStatus(event, 400); return null }
  const body = event.method === 'POST' ? await readBody(event).catch(() => ({})) : {}
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/invoices/${number}/nfe`,
    { method: 'POST', body },
  )
  setResponseStatus(event, status)
  return data
})
