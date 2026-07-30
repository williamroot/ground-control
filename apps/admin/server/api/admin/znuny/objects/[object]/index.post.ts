// Cria um objeto genérico do Znuny (Spec #4, Bloco A). Proxy fino: guard de
// allowlist, propaga o status do sidecar (201 sucesso, 422 recusa do Znuny
// com a mensagem — o operador precisa saber por quê).
export default defineEventHandler(async (event) => {
  const object = getRouterParam(event, 'object')
  if (!isZnunyObjectKey(object)) { setResponseStatus(event, 400); return null }
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, `/v1/admin/znuny/objects/${object}`, {
    method: 'POST',
    body,
  })
  setResponseStatus(event, status)
  return data
})
