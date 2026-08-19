export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'templateId')
  const { status, data } = await sidecarFetch(event, `/v1/admin/checklists/templates/${id}`, {
    method: 'DELETE',
  })
  setResponseStatus(event, status)
  return data
})
