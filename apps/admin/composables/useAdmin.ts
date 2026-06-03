// Sessão admin atual (Spec #1G-a, T1.E). Busca /api/admin/me UMA vez por request
// (useAsyncData dedupe pela key 'admin-me') — usada pela guarda de rota, pelo
// layout e pelas páginas. Retorna null quando não há sessão. Tipos congelados
// aqui para T1.E/T1.F consumirem sem divergir.
export interface AdminSession {
  agent_login: string
  role: 'gerti_staff'
}

export function useAdmin() {
  // Em SSR repassa o cookie da request original (carrega o `gsid_adm`).
  const headers = import.meta.server ? useRequestHeaders(['cookie']) : undefined
  return useAsyncData<AdminSession | null>('admin-me', () =>
    $fetch<AdminSession>('/api/admin/me', { headers }).catch(() => null))
}
