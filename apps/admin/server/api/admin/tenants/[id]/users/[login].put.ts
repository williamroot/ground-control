// Edita ou desativa uma pessoa do cliente (T-R2.1) — proxy fino.
//
// `login` é interpolado no path do sidecar, então o guard de path-injection
// roda ANTES de qualquer chamada (V-R2.7): um login com `../` subiria um nível
// e viraria requisição a outro endpoint, com o cookie de agente junto.
// Desativar é ValidID=2 no Znuny — nunca exclusão (invariante 3).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const login = getRouterParam(event, 'login')
  if (!isTenantId(id) || !isCustomerLogin(login)) { setResponseStatus(event, 404); return null }
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/users/${encodeURIComponent(login as string)}`,
    { method: 'PUT', body },
  )
  setResponseStatus(event, status)
  return data
})
