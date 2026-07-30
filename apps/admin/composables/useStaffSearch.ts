// Busca global do staff (Spec #3, V6) — lógica PURA. `path` vem pronto do
// sidecar em cada item; a UI usa como veio, sem concatenar nada (o protótipo
// tinha um bug de concatenação — ver contrato V6).

export const MIN_QUERY_LENGTH = 2
export const SEARCH_DEBOUNCE_MS = 300

export function shouldSearch(q: string): boolean {
  return q.trim().length >= MIN_QUERY_LENGTH
}

export interface SearchResultItem {
  id: string
  title: string
  subtitle?: string | null
  path: string
}

export interface StaffSearchResponse {
  tenants: SearchResultItem[]
  tickets: SearchResultItem[]
  kb: SearchResultItem[]
}

export interface SearchSection {
  key: keyof StaffSearchResponse
  label: string
  icon: string
}

export const SEARCH_SECTIONS: SearchSection[] = [
  { key: 'tenants', label: 'Clientes', icon: 'i-lucide-building-2' },
  { key: 'tickets', label: 'Chamados', icon: 'i-lucide-ticket' },
  { key: 'kb', label: 'Base de Conhecimento', icon: 'i-lucide-book-open' },
]

export function hasAnyResult(res: StaffSearchResponse | null | undefined): boolean {
  if (!res) return false
  return SEARCH_SECTIONS.some(s => (res[s.key]?.length ?? 0) > 0)
}
