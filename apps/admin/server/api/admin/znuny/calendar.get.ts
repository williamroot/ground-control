// Calendário do Znuny — jornada de trabalho e feriados (Spec #4, Bloco D).
// Proxy fino: repassa o calendário selecionado (''=padrão, '1'..'9') como
// query string. Contrato null=falha (igual ao portal/demais telas admin).
// Esta rota NÃO guarda nada — lê ao vivo do SysConfig via GI a cada chamada.
export default defineEventHandler(async (event) => {
  const query = getQuery(event)
  const calendar = typeof query.calendar === 'string' ? query.calendar : ''
  const qs = calendar ? `?calendar=${encodeURIComponent(calendar)}` : ''
  const { status, data } = await sidecarFetch(event, `/v1/admin/znuny/calendar${qs}`)
  if (status !== 200) { setResponseStatus(event, status); return null }
  return data
})
