// Tipo + default de branding COMPARTILHADOS entre server (middleware) e app
// (layout). Fica em shared/ porque a import-protection do Nuxt proíbe importar
// VALORES de server/ na parte Vue do app — só `import type` seria permitido.
// O layout precisa do VALOR DEFAULT_BRANDING como fallback, então ele mora aqui.

export interface Branding {
  display_name: string
  logo_url: string | null
  primary_color: string
  accent_color: string
  default_theme: string
  support_email: string | null
}

// Neutral safe default — NEVER the Gerti brand (Spec §2.2 / §6).
export const DEFAULT_BRANDING: Branding = {
  display_name: 'Portal',
  logo_url: null,
  primary_color: '#475569',
  accent_color: '#334155',
  default_theme: 'light',
  support_email: null,
}
