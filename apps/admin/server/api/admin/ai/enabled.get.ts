// Flag opt-in da IA (#1N) — proxy fino para o sidecar. O console esconde o painel
// de IA quando { enabled: false } (kill-switch global AI_FEATURES_ENABLED).
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/admin/ai/enabled')
  if (status !== 200) { setResponseStatus(event, status); return { enabled: false } }
  return data
})
