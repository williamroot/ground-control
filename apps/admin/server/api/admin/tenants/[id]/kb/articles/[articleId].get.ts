// Detalhe de um artigo (inclui body_markdown) — proxy fino (Spec #3, V1).
// Usado para pré-preencher o formulário de edição no console.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const articleId = getRouterParam(event, 'articleId')
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/kb/articles/${articleId}`,
  )
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
