// Lista dos calendários do Znuny com o nome gravado (teste V01, E1) — proxy
// fino. Forma do sidecar: `[{ value: 'default'|'1'..'9', name: string|null }]`.
// Contrato null=falha: a tela cai nos rótulos estáticos ("Calendário 3") e
// continua funcionando — o nome é conveniência, não requisito para editar.
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/admin/znuny/calendars')
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
