import type { H3Event } from 'h3'

// Fetch server-side para o sidecar. O checkout é PÚBLICO e cross-tenant
// (/v1/checkout/*) — não há cookie de sessão nem host de tenant a repassar.
export async function sidecarFetch<T>(
  event: H3Event,
  path: string,
  opts: { method?: string, body?: unknown, query?: Record<string, string> } = {},
): Promise<{ status: number, data: T | null }> {
  const cfg = useRuntimeConfig()
  const qs = opts.query
    ? '?' + new URLSearchParams(opts.query).toString()
    : ''
  const res = await fetch(`${cfg.sidecarUrl}${path}${qs}`, {
    method: opts.method || 'GET',
    headers: { 'content-type': 'application/json' },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  })
  let data: T | null = null
  try {
    data = (await res.json()) as T
  }
  catch {
    data = null
  }
  return { status: res.status, data }
}
