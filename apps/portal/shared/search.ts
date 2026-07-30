// Busca global federada (Spec #3 V6) — tipos e lógica pura compartilhados
// pela página `/busca`. `path` já vem PRONTO do backend em cada item; a
// página nunca concatena nada nele (o protótipo de referência tinha um bug
// de concatenação que gerava `/knowledge-basekb-001` — não repetir).

export interface SearchResultItem {
  id: string
  title: string
  subtitle: string | null
  path: string
}

export interface SearchResults {
  tickets: SearchResultItem[]
  assets: SearchResultItem[]
  kb: SearchResultItem[]
  catalog: SearchResultItem[]
}

export const SEARCH_MIN_LENGTH = 2
export const SEARCH_DEBOUNCE_MS = 300

// A busca só dispara a partir de 2 caracteres úteis (espaços nas pontas não contam).
export function isSearchableQuery(q: string): boolean {
  return q.trim().length >= SEARCH_MIN_LENGTH
}

export interface SearchSection {
  key: keyof SearchResults
  label: string
  items: SearchResultItem[]
}

const SECTION_LABELS: Record<keyof SearchResults, string> = {
  tickets: 'Chamados',
  assets: 'Ativos',
  kb: 'Base de Conhecimento',
  catalog: 'Catálogo',
}

const SECTION_ORDER: (keyof SearchResults)[] = ['tickets', 'assets', 'kb', 'catalog']

// Só as seções COM resultado — a página nunca renderiza uma seção vazia.
export function searchSections(results: SearchResults | null): SearchSection[] {
  if (!results) return []
  return SECTION_ORDER
    .map(key => ({ key, label: SECTION_LABELS[key], items: results[key] ?? [] }))
    .filter(s => s.items.length > 0)
}

export function searchTotal(results: SearchResults | null): number {
  if (!results) return 0
  return SECTION_ORDER.reduce((acc, key) => acc + (results[key]?.length ?? 0), 0)
}

// Debounce genérico (sem dependência externa): agrupa chamadas rápidas,
// executa só a última após `waitMs` de silêncio. `cancel()` para limpeza em
// onBeforeUnmount.
export function debounce<Args extends unknown[]>(
  fn: (...args: Args) => void,
  waitMs: number,
): { run: (...args: Args) => void, cancel: () => void } {
  let timer: ReturnType<typeof setTimeout> | null = null
  return {
    run: (...args: Args) => {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        timer = null
        fn(...args)
      }, waitMs)
    },
    cancel: () => {
      if (timer) {
        clearTimeout(timer)
        timer = null
      }
    },
  }
}
