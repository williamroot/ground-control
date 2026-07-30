// Spec #3 · V1 — pills de categoria da base de conhecimento (cliente).
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/kb/categories')
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
