// Headers a repassar nas fetches SSR que batem nos proxies /api/portal/* .
//
// O sidecar é multi-tenant: resolve o tenant pelo host (x-forwarded-host) e só
// então valida o gsid (que é tenant-scoped). Numa carga SSR/refresh, o $fetch
// interno do Nuxt para /api/portal/* NÃO carrega o host do tenant sozinho —
// se repassarmos só o cookie, o sidecarFetch manda host vazio/loopback, o
// sidecar não resolve o tenant e rejeita o gsid com 401. Resultado: a guarda
// useMe() vê me=null e redireciona p/ /login em QUALQUER refresh/abertura
// direta de página autenticada (no cliente funciona porque o browser manda o
// Host real). Por isso, no SSR, repassamos cookie + x-forwarded-host (derivado
// do host da request original). No cliente o browser já envia tudo → undefined.
export function useSidecarHeaders(): Record<string, string> | undefined {
  if (!import.meta.server) return undefined
  const h = useRequestHeaders(['cookie', 'x-forwarded-host', 'host'])
  const host = h['x-forwarded-host'] || h.host || ''
  const out: Record<string, string> = {}
  if (h.cookie) out.cookie = h.cookie
  if (host) out['x-forwarded-host'] = host
  return out
}
