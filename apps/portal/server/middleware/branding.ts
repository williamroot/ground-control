import type { H3Event } from 'h3'

export interface Branding {
  display_name: string
  logo_url: string | null
  primary_color: string
  accent_color: string
  default_theme: string
  support_email: string | null
}

// Neutral safe default — NEVER the Gerti brand (Spec §2.2 / §6).
export const DEFAULT_BRANDING: Branding = {
  display_name: 'Portal',
  logo_url: null,
  primary_color: '#475569',
  accent_color: '#334155',
  default_theme: 'light',
  support_email: null,
}

// Padrões aceitos (anchored):
//   1. <sub>.suporte.gerti.com.br  — produção
//   2. <sub>.suporte.was.dev.br    — testes 2-nível (Cloudflare Tunnel)
//   3. <sub>.was.dev.br            — testes 1-nível (Universal SSL *.was.dev.br)
const SUB_RE = /^([a-z0-9][a-z0-9-]{0,62})\.(?:suporte\.(?:gerti\.com\.br|was\.dev\.br)|was\.dev\.br)$/

// Infra was.dev.br 1-nível — não são tenants; resolvem para default.
const INFRA_HOSTS = new Set([
  'znuny-dev.was.dev.br',
  'api-dev.was.dev.br',
  'groundcontrol.was.dev.br',
])

export function resolveSubdomain(host: string, forwarded: string): string | null {
  const h = (forwarded || host || '').split(':')[0].toLowerCase()
  if (INFRA_HOSTS.has(h)) return null
  const m = SUB_RE.exec(h)
  return m ? m[1] : null
}

// Per-subdomain in-memory cache, 60s TTL (H12). Failure -> default, NOT cached.
const cache = new Map<string, { data: Branding, exp: number }>()
const TTL_MS = 60_000

export default defineEventHandler(async (event: H3Event) => {
  const sub = resolveSubdomain(
    getRequestHeader(event, 'host') || '',
    getRequestHeader(event, 'x-forwarded-host') || '',
  )
  if (!sub) {
    event.context.branding = DEFAULT_BRANDING
    return
  }
  const now = Date.now()
  const hit = cache.get(sub)
  if (hit && hit.exp > now) {
    event.context.branding = hit.data
    return
  }
  try {
    const { status, data } = await sidecarFetch<Branding>(event, '/v1/branding')
    if (status === 200 && data) {
      cache.set(sub, { data, exp: now + TTL_MS })
      event.context.branding = data
      return
    }
  }
  catch {
    // fall through to default
  }
  event.context.branding = DEFAULT_BRANDING
})
