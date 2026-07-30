// Lista de grupos/papéis do Znuny (Spec #4, Bloco C) — proxy fino. Alimenta o
// seletor de permissões da tela de agentes. Contrato null=falha.
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/admin/znuny/groups')
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
