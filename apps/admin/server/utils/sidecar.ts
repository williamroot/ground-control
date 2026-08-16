import type { H3Event } from 'h3'

// Proxy server-side para o sidecar (igual ao portal). Encaminha o Cookie de
// entrada (carrega o `gsid_adm` da sessão admin) e o X-Forwarded-Host. Os
// endpoints `/v1/admin/*` são cross-tenant: o sidecar pula a resolução de
// tenant para esse prefixo (TenantMiddleware), então o host não importa para
// o roteamento — mas mantemos o XFH por paridade com o portal.
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

// Passthrough binário (Onda 3): o PDF do relatório executivo não é JSON, então
// `sidecarFetch` não serve — ele tentaria parsear os bytes. Mesma forma do
// `sidecarFetchRaw` do portal, que já serve o PDF de fatura.
export async function sidecarFetchRaw(
  event: H3Event,
  path: string,
): Promise<{ status: number, body: ArrayBuffer, contentType: string }> {
  const cfg = useRuntimeConfig()
  const fwdHost
    = getRequestHeader(event, 'x-forwarded-host')
      || getRequestHeader(event, 'host')
      || ''
  const cookie = getRequestHeader(event, 'cookie') || ''
  const res = await fetch(`${cfg.sidecarUrl}${path}`, {
    method: 'GET',
    headers: { 'x-forwarded-host': fwdHost, cookie },
  })
  const body = await res.arrayBuffer()
  return {
    status: res.status,
    body,
    contentType: res.headers.get('content-type') || 'application/octet-stream',
  }
}
