// Catálogo de Serviços (Spec #3, V2) — lógica pura do formulário do console:
// rascunho, allowlist de ícone, validação (espelho leve do 422 do sidecar, que
// é a fonte de verdade) e montagem do payload. Fora dos componentes para
// testar sem montar o Nuxt (lição #1M..#1Q).

export const CATALOG_ICONS = [
  'ticket',
  'shield',
  'user-plus',
  'server',
  'package',
  'database',
  'box',
  'printer',
  'lock',
  'wifi',
  'mail',
  'settings',
] as const

export type CatalogIcon = typeof CATALOG_ICONS[number]

// Ícone Lucide usado no UI a partir do valor salvo (que é o nome "cru").
const ICON_TO_LUCIDE: Record<CatalogIcon, string> = {
  'ticket': 'i-lucide-ticket',
  'shield': 'i-lucide-shield',
  'user-plus': 'i-lucide-user-plus',
  'server': 'i-lucide-server',
  'package': 'i-lucide-package',
  'database': 'i-lucide-database',
  'box': 'i-lucide-box',
  'printer': 'i-lucide-printer',
  'lock': 'i-lucide-lock',
  'wifi': 'i-lucide-wifi',
  'mail': 'i-lucide-mail',
  'settings': 'i-lucide-settings',
}

export function catalogIconLucide(icon: string): string {
  return ICON_TO_LUCIDE[icon as CatalogIcon] ?? 'i-lucide-ticket'
}

export const CATALOG_ICON_OPTIONS = CATALOG_ICONS.map(i => ({ label: i, value: i }))

export interface CatalogItemDraft {
  name: string
  category: string
  description: string
  sla_hours: string
  icon: string
  znuny_queue: string
  znuny_service: string
  default_priority: string
  active: boolean
  sort_order: number
}

export interface CatalogItemRow {
  id: string
  name: string
  category: string
  description: string | null
  sla_hours: number | null
  icon: string
  znuny_queue: string | null
  znuny_service: string | null
  default_priority: string | null
  active: boolean
  sort_order: number
}

export function emptyCatalogDraft(): CatalogItemDraft {
  return {
    name: '',
    category: '',
    description: '',
    sla_hours: '',
    icon: 'ticket',
    znuny_queue: '',
    znuny_service: '',
    default_priority: '',
    active: true,
    sort_order: 0,
  }
}

export function catalogDraftFromItem(item: CatalogItemRow): CatalogItemDraft {
  return {
    name: item.name,
    category: item.category,
    description: item.description ?? '',
    sla_hours: item.sla_hours === null || item.sla_hours === undefined ? '' : String(item.sla_hours),
    icon: item.icon,
    znuny_queue: item.znuny_queue ?? '',
    znuny_service: item.znuny_service ?? '',
    default_priority: item.default_priority ?? '',
    active: item.active,
    sort_order: item.sort_order,
  }
}

/** Validação leve (espelho do server). Retorna lista de erros; vazia = válido. */
export function validateCatalogItem(draft: CatalogItemDraft): string[] {
  const errors: string[] = []
  const name = draft.name.trim()
  if (name.length < 3 || name.length > 120) errors.push('Nome deve ter entre 3 e 120 caracteres.')
  const category = draft.category.trim()
  if (category.length < 2 || category.length > 60) errors.push('Categoria deve ter entre 2 e 60 caracteres.')
  if (draft.description.trim().length > 1000) errors.push('Descrição deve ter no máximo 1000 caracteres.')
  if (draft.sla_hours.trim() !== '') {
    const n = Number(draft.sla_hours)
    if (!Number.isInteger(n) || n < 1 || n > 720) errors.push('SLA (horas) deve ser um número inteiro entre 1 e 720.')
  }
  if (!CATALOG_ICONS.includes(draft.icon as CatalogIcon)) errors.push('Ícone inválido.')
  if (draft.znuny_queue.trim().length > 200) errors.push('Fila Znuny deve ter no máximo 200 caracteres.')
  if (draft.znuny_service.trim().length > 200) errors.push('Serviço Znuny deve ter no máximo 200 caracteres.')
  if (draft.default_priority.trim().length > 200) errors.push('Prioridade padrão deve ter no máximo 200 caracteres.')
  if (!Number.isInteger(draft.sort_order) || draft.sort_order < 0 || draft.sort_order > 999) {
    errors.push('Ordem deve ser um número inteiro entre 0 e 999.')
  }
  return errors
}

export function isCatalogItemValid(draft: CatalogItemDraft): boolean {
  return validateCatalogItem(draft).length === 0
}

export interface CatalogItemPayload {
  name: string
  category: string
  description?: string
  sla_hours?: number
  icon: string
  znuny_queue?: string
  znuny_service?: string
  default_priority?: string
  active: boolean
  sort_order: number
}

export function buildCatalogItemPayload(draft: CatalogItemDraft): CatalogItemPayload {
  const description = draft.description.trim()
  const znunyQueue = draft.znuny_queue.trim()
  const znunyService = draft.znuny_service.trim()
  const defaultPriority = draft.default_priority.trim()
  return {
    name: draft.name.trim(),
    category: draft.category.trim(),
    description: description || undefined,
    sla_hours: draft.sla_hours.trim() === '' ? undefined : Number(draft.sla_hours),
    icon: draft.icon,
    znuny_queue: znunyQueue || undefined,
    znuny_service: znunyService || undefined,
    default_priority: defaultPriority || undefined,
    active: draft.active,
    sort_order: draft.sort_order,
  }
}
