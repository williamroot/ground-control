// Atualiza (ou invalida, com ValidID=2) um objeto genérico do Znuny (Spec #4,
// Bloco A). Proxy fino: guard de allowlist + id numérico, propaga o status do
// sidecar (200 sucesso, 404 id inexistente, 422 recusa do Znuny com mensagem).
export default defineEventHandler(async (event) => {
  const object = getRouterParam(event, 'object')
  const id = getRouterParam(event, 'id')
  if (!isZnunyObjectKey(object)) { setResponseStatus(event, 400); return null }
  if (!isNumericId(id)) { setResponseStatus(event, 400); return null }
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, `/v1/admin/znuny/objects/${object}/${id}`, {
    method: 'PUT',
    body,
  })
  setResponseStatus(event, status)
  return data
})
