// Grava as filas do cliente (T-R5.2) — proxy fino. O 422 do sidecar traz o
// motivo (fila que não existe no Znuny, ou marcação de padrão errada) e é
// repassado inteiro para a tela mostrar em português.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!isTenantId(id)) { setResponseStatus(event, 404); return null }
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/queues`,
    { method: 'PUT', body },
  )
  setResponseStatus(event, status)
  return data
})
