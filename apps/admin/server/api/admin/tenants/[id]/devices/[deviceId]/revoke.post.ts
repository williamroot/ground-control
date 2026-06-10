// Revoga um dispositivo (#1R-a): heartbeats subsequentes recebem 401.
// Proxy fino com guard de uuid no deviceId. Propaga o status do sidecar.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const deviceId = getRouterParam(event, 'deviceId')
  if (!/^[0-9a-fA-F-]{36}$/.test(deviceId ?? '')) { setResponseStatus(event, 400); return null }
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/devices/${deviceId}/revoke`,
    { method: 'POST' },
  )
  setResponseStatus(event, status)
  return data
})
