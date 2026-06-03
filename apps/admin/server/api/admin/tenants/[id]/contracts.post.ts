// Criação de contrato p/ um cliente — proxy fino (#1G-a T1.F). Propaga o status
// do sidecar (201 sucesso, 404 tenant inexistente, 409 código duplicado).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/contracts`,
    { method: 'POST', body },
  )
  setResponseStatus(event, status)
  return data
})
