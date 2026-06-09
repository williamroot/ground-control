// #1M — proxy server-side do CSAT. Mesmo padrão de reply.post.ts: guard de id
// numérico (anti path-injection), repasse via sidecarFetch, status passthrough.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!/^[0-9]+$/.test(id ?? '')) { setResponseStatus(event, 400); return null }
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, `/v1/tickets/${id}/csat`, {
    method: 'POST',
    body,
  })
  setResponseStatus(event, status)
  return data
})
