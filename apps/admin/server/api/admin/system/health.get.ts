// Saúde do sistema (Spec #3, V6) — proxy fino. O sidecar isola a falha de
// cada sonda (HTTP sempre 200 quando o endpoint responde); se o endpoint
// inteiro cair, devolvemos null para a página mostrar o card de erro em vez
// de tela branca.
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/admin/system/health')
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
