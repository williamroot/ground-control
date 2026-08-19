export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const poolId = getRouterParam(event, 'poolId')
  const contractId = getRouterParam(event, 'contractId')
  const { status, data } = await sidecarFetch(
    event,
    `/v1/admin/tenants/${id}/credit-pools/${poolId}/contracts/${contractId}`,
    { method: 'DELETE' },
  )
  setResponseStatus(event, status)
  return data
})
