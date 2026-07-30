// Mapa de ícones do catálogo de serviços (Spec #3 · V2) — allowlist estrita.
// O backend valida a mesma allowlist no `icon` do item (422 fora dela); aqui
// replicamos o guard no front para nunca resolver um ícone fora do controle
// do design system, mesmo que o dado chegue inesperado (defeito no proxy,
// campo antigo, etc). Fora da lista → fallback 'i-lucide-ticket'.
export const CATALOG_ICON_ALLOWLIST = [
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

export type CatalogIconKey = typeof CATALOG_ICON_ALLOWLIST[number]

const FALLBACK_ICON = 'i-lucide-ticket'

function isCatalogIconKey(v: string): v is CatalogIconKey {
  return (CATALOG_ICON_ALLOWLIST as readonly string[]).includes(v)
}

/** `icon` cru do sidecar → nome `i-lucide-*` do Nuxt UI. Fora da allowlist → fallback. */
export function catalogIconName(icon: string | null | undefined): string {
  const v = (icon ?? '').trim().toLowerCase()
  return isCatalogIconKey(v) ? `i-lucide-${v}` : FALLBACK_ICON
}
