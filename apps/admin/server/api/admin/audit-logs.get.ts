// Trilha de auditoria (Spec #3, V5) — proxy fino, cross-tenant. Repassa os
// filtros de query como vieram (q, action, tenant_id, from, to, limit,
// offset); o sidecar é a fonte da verdade da validação (limit máx. 200 -> 422).
export default defineEventHandler(async (event) => {
  const query = getQuery(event)
  const qs = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    qs.set(key, String(value))
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const { status, data } = await sidecarFetch(event, `/v1/admin/audit-logs${suffix}`)
  setResponseStatus(event, status)
  return data
})
