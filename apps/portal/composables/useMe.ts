// Sessão atual do portal (Spec #1H). Busca /api/portal/me UMA vez por request
// (useAsyncData dedupe pela key 'me') — usado pela guarda global, pelo layout
// (nav por papel) e pelas páginas. Retorna null quando não há sessão.
// R7 (Onda 5) — `approver` entrou junto com a aprovação de chamados. Ele NÃO
// é um admin reduzido: só decide pedidos, e não vê contratos nem faturas.
export type PortalRole = 'admin' | 'helpdesk' | 'approver'

export interface Me {
  tenant_id: string
  display_name: string
  customer_login: string
  role: PortalRole
}

export function useMe() {
  // Em SSR repassa cookie + host do tenant (x-forwarded-host) — sem o host o
  // sidecar não resolve o tenant e rejeita o gsid (401). Ver useSidecarHeaders.
  const headers = useSidecarHeaders()
  return useAsyncData<Me | null>('me', () =>
    $fetch<Me>('/api/portal/me', { headers }).catch(() => null))
}
