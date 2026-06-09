// Rótulos/cores compartilhados de ativos (CMDB #1K) — DRY entre lista e detalhe.
// Cores: tokens SEMÂNTICOS do Nuxt UI (info/success/warning/error/neutral).
// NUNCA a cor da marca (H8) — esta é informação de estado, não de identidade.
export type BadgeColor = 'success' | 'warning' | 'error' | 'info' | 'neutral'

// Estado de implantação (deploy_state) do Config Item. Em produção =
// success; planejamento/manutenção = warning; retirado/expirado = neutral.
export function deployStateColor(state: string | null | undefined): BadgeColor {
  const s = (state ?? '').toLowerCase()
  if (!s) return 'neutral'
  if (/(produc|production|active|ativo)/.test(s)) return 'success'
  if (/(maint|manuten|plan|test|pilot|repair)/.test(s)) return 'warning'
  if (/(retir|decommiss|inactive|inativo|expir|scrap)/.test(s)) return 'neutral'
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
