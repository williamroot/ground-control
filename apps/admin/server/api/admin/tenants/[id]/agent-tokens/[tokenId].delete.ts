// Desabilita um token de instalação (#1R-a, rotação = novo + desabilita antigo).
// Proxy fino com guard de uuid no tokenId. Propaga o status do sidecar.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const tokenId = getRouterParam(event, 'tokenId')
  if (!/^[0-9a-fA-F-]{36}$/.test(tokenId ?? '')) { setResponseStatus(event, 400); return null }
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/agent-tokens/${tokenId}`,
    { method: 'DELETE' },
  )
  setResponseStatus(event, status)
  return data
})
