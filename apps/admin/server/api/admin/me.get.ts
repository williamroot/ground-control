// Presença da sessão admin (Spec #1G-a, T1.E). NÃO existe `/v1/admin/me` no
// sidecar — derivamos a presença da sessão de forma barata batendo num endpoint
// admin autenticado (`GET /v1/admin/tenants`):
//   • 200 → há sessão válida. Não temos o agent_login no server-side a partir
//     desse endpoint, então devolvemos uma sessão mínima `{role:'gerti_staff'}`
//     (presença = "autenticado"). O campo agent_login fica vazio por ora.
//   • !=200 (tipicamente 401) → sem sessão: propaga o status e devolve null.
// Mantido simples de propósito: o objetivo é "existe sessão admin válida?".
// Forma do retorno casa com `AdminSession` (composables/useAdmin.ts).
export default defineEventHandler(async (event) => {
  const { status } = await sidecarFetch<unknown>(event, '/v1/admin/tenants')
  if (status !== 200) {
    setResponseStatus(event, status)
    return null
  }
  return { agent_login: '', role: 'gerti_staff' as const }
})
