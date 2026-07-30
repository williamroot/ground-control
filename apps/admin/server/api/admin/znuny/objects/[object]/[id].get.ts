// Detalhe de um objeto genérico do Znuny (Spec #4, Bloco A). Guard de
// allowlist no objeto e de formato numérico no id — malformado é 400, nunca
// chega a chamar o sidecar.
export default defineEventHandler(async (event) => {
  const object = getRouterParam(event, 'object')
  const id = getRouterParam(event, 'id')
  if (!isZnunyObjectKey(object)) { setResponseStatus(event, 400); return null }
  if (!isNumericId(id)) { setResponseStatus(event, 400); return null }
  const { status, data } = await sidecarFetch(event, `/v1/admin/znuny/objects/${object}/${id}`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
