// Domínios autorizados (T-R9.5/T-R9.7) — proxy fino. É a "visão centralizada
// dos domínios de todos os clientes" que o Kleber pede em 06:19.
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/admin/znuny/postmaster-filters')
  setResponseStatus(event, status)
  return data
})
