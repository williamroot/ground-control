// Sessão admin atual (Spec #1G-a). STUB da Fase 0 — T1.E preenche (busca
// /api/admin/me UMA vez por request; retorna null sem sessão). Tipos congelados
// aqui para T1.E/T1.F consumirem sem divergir.
export interface AdminSession {
  agent_login: string
  role: 'gerti_staff'
}

export function useAdmin() {
  return useAsyncData<AdminSession | null>('admin-me', () =>
    Promise.resolve(null))
}
