// Identidade FIXA do Console de Administração Gerti (Spec #1G-a). NÃO é
// white-label: o admin é a casa da equipe Gerti/WAS. Compartilhado entre
// server e app (em shared/ por causa da import-protection do Nuxt).

export const ADMIN_IDENTITY = {
  display_name: 'Gerti · Console de Administração',
  short_name: 'Gerti',
  primary_color: '#4f46e5',
  accent_color: '#4338ca',
} as const

// Nome do cookie da sessão admin — DEVE casar com `admin_session_cookie_name`
// do sidecar (config.py) e ser DISTINTO do `gsid` do portal de cliente.
export const ADMIN_COOKIE = 'gsid_adm'
