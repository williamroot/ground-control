// Lista de classes de CI do Znuny (Spec #4, Bloco B) — proxy fino. Contrato
// null=falha (igual ao portal): a página distingue erro de vazio pelo `null`.
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/admin/znuny/ci-classes')
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
