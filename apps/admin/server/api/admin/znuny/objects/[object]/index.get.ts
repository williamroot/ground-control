// Lista de objetos genéricos do Znuny (Spec #4, Bloco A) — Queue/SLA/Service/
// Type/State/Priority. Proxy fino: guard de allowlist antes de chamar o
// sidecar (defesa em profundidade, o Perl também valida). Contrato null=falha
// (igual ao portal). O corpo traz os itens + listas de apoio (grupos,
// calendários, validade etc.) que a UI usa para montar selects.
export default defineEventHandler(async (event) => {
  const object = getRouterParam(event, 'object')
  if (!isZnunyObjectKey(object)) { setResponseStatus(event, 400); return null }
  const { status, data } = await sidecarFetch(event, `/v1/admin/znuny/objects/${object}`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
