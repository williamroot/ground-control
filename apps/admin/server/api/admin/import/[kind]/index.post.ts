// Execução da importação (T-R8.2) — idempotente por linha no sidecar.
export default defineEventHandler(async (event) => {
  const kind = getRouterParam(event, 'kind')
  if (!isImportKind(kind)) { setResponseStatus(event, 404); return null }
  const tenantId = String(getQuery(event).tenant_id ?? '')
  if (kind === 'tenant_users' && !isTenantId(tenantId)) {
    setResponseStatus(event, 422)
    return { detail: 'escolha o cliente dono dos usuários' }
  }
  const parts = await readMultipartFormData(event)
  const file = parts?.find(p => p.name === 'file' && p.filename)
  if (!file) { setResponseStatus(event, 422); return { detail: 'envie o arquivo CSV' } }
  const qs = kind === 'tenant_users' ? `?tenant_id=${encodeURIComponent(tenantId)}` : ''
  const { status, data } = await sidecarUpload(event, `/v1/admin/import/${kind}${qs}`, {
    name: 'file',
    filename: file.filename!,
    type: file.type || 'text/csv',
    data: file.data,
  })
  setResponseStatus(event, status)
  return data
})
