// Sessão atual do portal (Spec #1H). Busca /api/portal/me UMA vez por request
// (useAsyncData dedupe pela key 'me') — usado pela guarda global, pelo layout
// (nav por papel) e pelas páginas. Retorna null quando não há sessão.
export type PortalRole = 'admin' | 'helpdesk'

export interface Me {
  tenant_id: string
  display_name: string
  customer_login: string
  role: PortalRole
}

export function useMe() {
  // Em SSR repassa o cookie da request original (igual aos demais fetches).
  const headers = import.meta.server ? useRequestHeaders(['cookie']) : undefined
  return useAsyncData<Me | null>('me', () =>
    $fetch<Me>('/api/portal/me', { headers }).catch(() => null))
}
