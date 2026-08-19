// Edita uma caixa de recebimento (T-R9.4/T-R9.7) — proxy fino.
// Corpo sem `password` significa "manter a senha atual": é o que deixa o
// operador trocar a fila de uma caixa sem nunca ter conhecido a senha dela.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!isNumericId(id)) { setResponseStatus(event, 404); return null }
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/znuny/mail-accounts/${id}`,
    { method: 'PUT', body },
  )
  setResponseStatus(event, status)
  return data
})
