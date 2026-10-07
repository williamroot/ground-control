// Ciclos fechados ainda sem fatura, para o seletor da tela de faturas (teste
// V01, B5) — proxy fino. Antes a tela pedia o UUID do ciclo, que ninguém de
// fora consegue fornecer. O filtro é fixo (`uninvoiced=true`): é o único uso
// do console, e não abrimos uma query livre para o sidecar sem precisar.
// O sidecar escopa pelo tenant da rota; contrato null=falha.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${encodeURIComponent(id ?? '')}/billing-cycles?uninvoiced=true`,
  )
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
