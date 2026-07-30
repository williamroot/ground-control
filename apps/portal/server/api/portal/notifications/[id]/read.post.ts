// #3 V3 — marca uma notificação como lida. Guard de formato UUID antes de
// repassar ao sidecar (anti path-injection, mesmo padrão de reply.post.ts/
// csat.post.ts, mas aqui o id é UUID e não numérico).
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!UUID_RE.test(id ?? '')) { setResponseStatus(event, 400); return null }
  const { status, data } = await sidecarFetch(event, `/v1/notifications/${id}/read`, {
    method: 'POST',
  })
  setResponseStatus(event, status)
  return data
})
