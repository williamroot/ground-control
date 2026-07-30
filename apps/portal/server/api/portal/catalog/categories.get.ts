// Spec #3 · V2 — pills de categoria do catálogo de serviços (cliente).
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/catalog/categories')
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
