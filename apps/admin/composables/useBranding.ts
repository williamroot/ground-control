// Editor de identidade visual do tenant (Spec #3, V4). Lógica PURA (sem
// Nuxt/DOM), testável isoladamente. A verdade é o 422 do sidecar — isto aqui
// é só feedback imediato de UX, espelhando as validações do backend
// (docs/superpowers/plans/2026-07-30-spec-3-paridade-grounddesk.md, V4).

export type DefaultTheme = 'light' | 'dark' | 'system'

export interface BrandingDraft {
  display_name: string
  primary_color: string
  accent_color: string
  logo_url: string
  default_theme: DefaultTheme
}

export const HEX_COLOR_RE = /^#[0-9A-Fa-f]{6}$/
export const THEME_OPTIONS: DefaultTheme[] = ['light', 'dark', 'system']

export function emptyBrandingDraft(): BrandingDraft {
  return {
    display_name: '',
    primary_color: '#4f46e5',
    accent_color: '#4338ca',
    logo_url: '',
    default_theme: 'system',
  }
}

export function validateHexColor(value: string): boolean {
  return HEX_COLOR_RE.test(value.trim())
}

// logo_url é opcional; quando informada, precisa ser https:// e <=500 chars.
export function validateLogoUrl(value: string): boolean {
  const v = value.trim()
  if (!v) return true
  if (v.length > 500) return false
  return v.startsWith('https://')
}

export type BrandingErrors = Partial<Record<keyof BrandingDraft, string>>

export function validateBrandingDraft(draft: BrandingDraft): BrandingErrors {
  const errors: BrandingErrors = {}
  const name = draft.display_name.trim()
  if (name.length < 2 || name.length > 80) {
    errors.display_name = 'Nome de exibição deve ter entre 2 e 80 caracteres.'
  }
  if (!validateHexColor(draft.primary_color)) {
    errors.primary_color = 'Cor primária precisa ser um hexadecimal no formato #RRGGBB.'
  }
  if (!validateHexColor(draft.accent_color)) {
    errors.accent_color = 'Cor de destaque precisa ser um hexadecimal no formato #RRGGBB.'
  }
  if (!validateLogoUrl(draft.logo_url)) {
    errors.logo_url = 'URL do logo precisa começar com https:// e ter até 500 caracteres.'
  }
  if (!THEME_OPTIONS.includes(draft.default_theme)) {
    errors.default_theme = 'Tema padrão inválido.'
  }
  return errors
}

export function isBrandingValid(draft: BrandingDraft): boolean {
  return Object.keys(validateBrandingDraft(draft)).length === 0
}

export function buildBrandingPayload(draft: BrandingDraft): {
  display_name: string
  primary_color: string
  accent_color: string
  logo_url: string | null
  default_theme: DefaultTheme
} {
  return {
    display_name: draft.display_name.trim(),
    primary_color: draft.primary_color.trim(),
    accent_color: draft.accent_color.trim(),
    logo_url: draft.logo_url.trim() ? draft.logo_url.trim() : null,
    default_theme: draft.default_theme,
  }
}

// Erro 422 do FastAPI (Pydantic) chega como {detail: [{loc:[...,"campo"], msg}]}.
// Erro de domínio (ex.: tenant_not_found) chega como {detail: "mensagem"}.
// Convertemos o primeiro formato num mapa campo -> mensagem para colocar o
// erro ao lado do campo certo; o segundo vira uma mensagem geral (chave '').
export function parseValidationErrors(detail: unknown): Record<string, string> {
  const out: Record<string, string> = {}
  if (Array.isArray(detail)) {
    for (const d of detail) {
      const entry = d as { loc?: unknown[], msg?: unknown }
      const loc = Array.isArray(entry.loc) ? entry.loc : []
      const field = String(loc.at(-1) ?? '')
      if (field) out[field] = String(entry.msg ?? 'Valor inválido.')
    }
    return out
  }
  if (typeof detail === 'string' && detail) {
    out[''] = detail
  }
  return out
}
