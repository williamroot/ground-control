// Metadados de automação (#1Q) — proxy fino p/ os dropdowns da UI.
export default defineEventHandler(async (event) => {
  const { status, data } = await sidecarFetch(event, '/v1/admin/automation/meta')
  if (status !== 200) {
    setResponseStatus(event, status)
    return null
  }
  return data
})
