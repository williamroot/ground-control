// Remove uma regra de domínio (T-R9.5) — proxy fino.
//
// Este é o ÚNICO caminho de exclusão real da capa de administração: o filtro
// de PostMaster não tem `ValidID`, então não há como invalidar. Exceção
// declarada à invariante 3, e o sidecar grava o estado anterior completo na
// auditoria antes de o objeto sumir.
export default defineEventHandler(async (event) => {
  const name = getRouterParam(event, 'name')
  if (!isFilterName(name)) { setResponseStatus(event, 404); return null }
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/znuny/postmaster-filters/${encodeURIComponent(name as string)}`,
    { method: 'DELETE' },
  )
  setResponseStatus(event, status)
  return data
})
