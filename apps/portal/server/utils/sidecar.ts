import type { H3Event } from 'h3'

// Server-side fetch to the sidecar. Forwards the resolved tenant host via
// X-Forwarded-Host (undici/Node fetch FORBIDS overriding the Host header —
// it silently rewrites it to the target authority `sidecar:8001`, so the
// sidecar would never see the tenant subdomain) and the inbound Cookie so
// TenantMiddleware resolves the subdomain (H9) and the gsid session
// round-trips (H8).
export async function sidecarFetch<T>(
  event: H3Event,
  path: string,
  opts: { method?: string, body?: unknown } = {},
): Promise<{ status: number, data: T | null, setCookie: string[] }> {
  const cfg = useRuntimeConfig()
  const fwdHost
    = getRequestHeader(event, 'x-forwarded-host')
      || getRequestHeader(event, 'host')
      || ''
  const cookie = getRequestHeader(event, 'cookie') || ''
  const res = await fetch(`${cfg.sidecarUrl}${path}`, {
    method: opts.method || 'GET',
    headers: {
      'x-forwarded-host': fwdHost,
      'cookie': cookie,
      'content-type': 'application/json',
    },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  })
  const setCookie = res.headers.getSetCookie?.() ?? []
  let data: T | null = null
  try {
    data = (await res.json()) as T
  }
  catch {
    data = null
  }
  return { status: res.status, data, setCookie }
}
