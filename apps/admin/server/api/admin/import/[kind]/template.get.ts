// Modelo CSV (T-R8.4) — passthrough de texto, com allowlist de tipo.
export default defineEventHandler(async (event) => {
  const kind = getRouterParam(event, 'kind')
  if (!isImportKind(kind)) { setResponseStatus(event, 404); return null }
  const { status, body, contentType } = await sidecarFetchRaw(
    event, `/v1/admin/import/${kind}/template`,
  )
  if (status !== 200) { setResponseStatus(event, status); return null }
  setResponseHeader(event, 'content-type', contentType)
  setResponseHeader(event, 'content-disposition', `attachment; filename="modelo-${kind}.csv"`)
  return new Uint8Array(body)
})
