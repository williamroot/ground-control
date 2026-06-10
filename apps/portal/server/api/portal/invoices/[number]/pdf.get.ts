// Proxy do PDF da fatura: guard numérico (anti path-injection) + passthrough
// dos bytes/content-type do sidecar (resposta binária, sem JSON).
export default defineEventHandler(async (event) => {
  const number = getRouterParam(event, 'number')
  if (!/^[0-9]+$/.test(number ?? '')) { setResponseStatus(event, 400); return null }
  const { status, body, contentType } = await sidecarFetchRaw(
    event,
    `/v1/invoices/${number}/pdf`,
  )
  if (status !== 200) { setResponseStatus(event, status); return null }
  setResponseStatus(event, 200)
  setResponseHeader(event, 'content-type', contentType)
  setResponseHeader(event, 'content-disposition', `inline; filename="fatura-${number}.pdf"`)
  return new Uint8Array(body)
})
