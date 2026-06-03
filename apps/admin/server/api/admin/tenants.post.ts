// Onboarding de cliente (tenant + branding + usuários) — proxy fino (#1G-a T1.F).
// Encaminha o corpo e propaga o status do sidecar (201 sucesso, 409 duplicado,
// 503 znuny indisponível) para a UI tratar.
export default defineEventHandler(async (event) => {
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, '/v1/admin/tenants', {
    method: 'POST',
    body,
  })
  setResponseStatus(event, status)
  return data
})
