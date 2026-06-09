// Rótulos/cores compartilhados de ativos (CMDB #1K) — DRY entre lista e detalhe.
// Cores: tokens SEMÂNTICOS do Nuxt UI (info/success/warning/error/neutral).
// NUNCA a cor da marca (H8) — esta é informação de estado, não de identidade.
export type BadgeColor = 'success' | 'warning' | 'error' | 'info' | 'neutral'

// Estado de implantação (deploy_state) do Config Item. Em produção =
// success; planejamento/manutenção = warning; retirado/expirado = neutral.
export function deployStateColor(state: string | null | undefined): BadgeColor {
  const s = (state ?? '').toLowerCase()
  if (!s) return 'neutral'
  // Retirado/inativo antes de "ativo" — "inactive" contém "active".
  if (/(retir|decommiss|inactive|inativo|expir|scrap)/.test(s)) return 'neutral'
  if (/(produc|production|active|ativo)/.test(s)) return 'success'
  if (/(maint|manuten|plan|test|pilot|repair)/.test(s)) return 'warning'
  return 'info'
}

// Estado de incidente (inci_state) do Config Item. Operacional = success;
// degradado/aviso = warning; incidente/falha = error.
export function inciStateColor(state: string | null | undefined): BadgeColor {
  const s = (state ?? '').toLowerCase()
  if (!s) return 'neutral'
  if (/(operac|operational|ok|normal)/.test(s)) return 'success'
  if (/(warn|degrad|aviso|aten)/.test(s)) return 'warning'
  if (/(incid|fail|falha|down|critical|critic|erro)/.test(s)) return 'error'
  return 'neutral'
}

// Rótulos PT-BR das chaves de `attributes` do Config Item (#1L fase 2).
// Chave desconhecida cai no próprio nome cru via assetAttrLabel().
export const ASSET_ATTR_LABELS: Record<string, string> = {
  OperatingSystem: 'Sistema operacional',
  Vendor: 'Fabricante',
  Model: 'Modelo',
  SerialNumber: 'Nº de série',
  CPU: 'CPU',
  Memoria: 'Memória',
  Disco: 'Disco',
  Description: 'Descrição',
  NetworkAddress: 'Endereço de rede',
  Version: 'Versão',
}

// Ordem preferida das chaves conhecidas; o resto vem depois em ordem alfabética.
export const ASSET_ATTR_ORDER: string[] = [
  'OperatingSystem', 'Vendor', 'Model', 'SerialNumber', 'CPU',
  'Memoria', 'Disco', 'NetworkAddress', 'Version', 'Description',
]

export function assetAttrLabel(key: string): string {
  return ASSET_ATTR_LABELS[key] ?? key
}
