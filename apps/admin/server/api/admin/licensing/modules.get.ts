// Catálogo FECHADO de módulos — a tela monta o seletor com isto, nunca com
// strings soltas no template.
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/admin/licensing/modules')
  setResponseStatus(event, status)
  return data
})
