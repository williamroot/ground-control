import type { H3Event } from 'h3'

// Server-side fetch to the sidecar. Forwards the resolved tenant host via
// X-Forwarded-Host (undici/Node fetch FORBIDS overriding the Host header —
// it silently rewrites it to the target authority `sidecar:8001`, so the
// sidecar would never see the tenant subdomain) and the inbound Cookie so
// TenantMiddleware resolves the subdomain (H9) and the gsid session
// round-trips (H8).
//
// opts.rawBody + opts.contentType: raw passthrough (e.g. multipart/form-data).
// When rawBody is provided the body is sent AS-IS and content-type is set to
// opts.contentType (the original boundary is preserved). When absent, the
// current JSON behavior is unchanged.
export async function sidecarFetch<T>(
  event: H3Event,
  path: string,
  opts: {
    method?: string
    body?: unknown
    rawBody?: Uint8Array
    contentType?: string
  } = {},
): Promise<{ status: number, data: T | null, setCookie: string[] }> {
  const cfg = useRuntimeConfig()
  const fwdHost
    = getRequestHeader(event, 'x-forwarded-host')
      || getRequestHeader(event, 'host')
      || ''
  const cookie = getRequestHeader(event, 'cookie') || ''

  const useRaw = opts.rawBody !== undefined
  // Uint8Array is not in BodyInit for this TS lib target — lift to ArrayBuffer.
  const rawBodyInit: BodyInit | undefined = opts.rawBody
    ? opts.rawBody.buffer.slice(opts.rawBody.byteOffset, opts.rawBody.byteOffset + opts.rawBody.byteLength) as ArrayBuffer
    : undefined
  const res = await fetch(`${cfg.sidecarUrl}${path}`, {
    method: opts.method || 'GET',
    headers: {
      'x-forwarded-host': fwdHost,
      'cookie': cookie,
      'content-type': useRaw ? (opts.contentType ?? 'application/octet-stream') : 'application/json',
    },
    body: useRaw ? rawBodyInit : (opts.body ? JSON.stringify(opts.body) : undefined),
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
