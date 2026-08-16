// Chamados de um cliente, para a aba da ficha (T-R1.6) — proxy fino.
//
// O backend já sabia filtrar por cliente (`GET /v1/admin/tickets?customer_id=`);
// faltava a tela. Resolvemos o `znuny_customer_id` a partir do tenant aqui, no
// servidor, para a página não precisar conhecer a chave do Znuny — e para um
// id de tenant inválido morrer antes de virar chamada.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!isTenantId(id)) { setResponseStatus(event, 404); return null }

  const tenant = await sidecarFetch<{ znuny_customer_id?: string }>(
    event,
    `/v1/admin/tenants/${id}`,
  )
  if (tenant.status !== 200 || !tenant.data?.znuny_customer_id) {
    setResponseStatus(event, tenant.status === 200 ? 404 : tenant.status)
    return null
  }

  const customerId = encodeURIComponent(tenant.data.znuny_customer_id)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tickets?customer_id=${customerId}`,
  )
  setResponseStatus(event, status)
  return data
})
