// Simulação da importação (T-R8.1) — encaminha o CSV e NÃO grava nada.
export default defineEventHandler(async (event) => {
  const kind = getRouterParam(event, 'kind')
  if (!isImportKind(kind)) { setResponseStatus(event, 404); return null }
  const parts = await readMultipartFormData(event)
  const file = parts?.find(p => p.name === 'file' && p.filename)
  if (!file) { setResponseStatus(event, 422); return { detail: 'envie o arquivo CSV' } }
  const { status, data } = await sidecarUpload(event, `/v1/admin/import/${kind}/validate`, {
    name: 'file',
    filename: file.filename!,
    type: file.type || 'text/csv',
    data: file.data,
  })
  setResponseStatus(event, status)
  return data
})
