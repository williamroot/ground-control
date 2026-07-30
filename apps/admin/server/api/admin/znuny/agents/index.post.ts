// Cria um agente no Znuny (Spec #4, Bloco C) — proxy fino. O corpo NUNCA traz
// senha (definir senha é ação separada, ver `[id].put.ts`). Propaga o status
// do sidecar (201 sucesso, 422 recusa com a mensagem do Znuny).
export default defineEventHandler(async (event) => {
  const body = await readBody(event)
  const { status, data } = await sidecarFetch(event, '/v1/admin/znuny/agents', {
    method: 'POST',
    body,
  })
  setResponseStatus(event, status)
  return data
})
