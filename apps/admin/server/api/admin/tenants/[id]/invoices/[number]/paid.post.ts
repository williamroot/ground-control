// Marca fatura como paga — proxy fino (#1P). Guard numérico no number.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const number = getRouterParam(event, 'number')
  if (!/^[0-9]+$/.test(number ?? '')) { setResponseStatus(event, 400); return null }
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/invoices/${number}/paid`,
    { method: 'POST' },
  )
  setResponseStatus(event, status)
  return data
})
