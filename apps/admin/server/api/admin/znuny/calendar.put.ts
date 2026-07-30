// Grava a jornada de trabalho e/ou feriados no Znuny (Spec #4, Bloco D) —
// tela de MAIOR RISCO do console: o sidecar faz SettingLock -> SettingUpdate
// -> ConfigurationDeploy e libera o lock mesmo em erro (nunca aplica
// parcial). Proxy fino: propaga o status (200 ok, 422 forma inválida ou
// Znuny recusou — com a mensagem, 503 Znuny fora do ar).
export default defineEventHandler(async (event) => {
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, '/v1/admin/znuny/calendar', {
    method: 'PUT',
    body,
  })
  setResponseStatus(event, status)
  return data
})
