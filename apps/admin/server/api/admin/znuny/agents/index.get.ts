// Lista de agentes do Znuny (Spec #4, Bloco C) — proxy fino. O sidecar NUNCA
// devolve hash de senha nesta rota (nem em nenhuma outra). Contrato null=falha.
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/admin/znuny/agents')
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
