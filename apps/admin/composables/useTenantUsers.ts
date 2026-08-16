// Usuários do cliente (T-R2.5, R2 do vídeo do Kleber). Lógica PURA.
//
// O ponto do requisito é que existe UM cadastro por pessoa, que serve para o
// portal e para o e-mail — no TIFLUX são dois, e os chamados que entram por
// e-mail nunca aparecem no portal de quem os mandou. A tela precisa dizer isso
// com todas as letras, e é por isso que o texto abaixo mora aqui, junto da
// lógica, e não perdido no template.

export const CADASTRO_UNICO_HINT
  = 'Este usuário abre chamados pelo portal e por e-mail — é o mesmo cadastro.'

export type PortalRole = 'admin' | 'helpdesk'

export interface TenantUser {
  customer_login: string
  first_name: string
  last_name: string
  email: string
  phone: string
  mobile: string
  extension: string | null
  active: boolean
  role: PortalRole | null
  email_intake_enabled: boolean | null
  has_portal_access: boolean
}

export interface TenantUserDraft {
  email: string
  first_name: string
  last_name: string
  password: string
  role: PortalRole
  phone: string
  mobile: string
  extension: string
  active: boolean
  email_intake_enabled: boolean
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function emptyUserDraft(): TenantUserDraft {
  return {
    email: '',
    first_name: '',
    last_name: '',
    password: '',
    role: 'helpdesk',
    phone: '',
    mobile: '',
    extension: '',
    active: true,
    email_intake_enabled: true,
  }
}

export function draftFromUser(u: TenantUser): TenantUserDraft {
  return {
    email: u.email || u.customer_login,
    first_name: u.first_name,
    last_name: u.last_name,
    password: '',
    role: u.role ?? 'helpdesk',
    phone: u.phone,
    mobile: u.mobile,
    extension: u.extension ?? '',
    active: u.active,
    email_intake_enabled: u.email_intake_enabled ?? true,
  }
}

/** Erros em português. Lista vazia = pode salvar. `isEdit` dispensa a senha. */
export function validateUserDraft(
  draft: Partial<TenantUserDraft>,
  { isEdit = false }: { isEdit?: boolean } = {},
): string[] {
  const errors: string[] = []
  const email = (draft.email ?? '').trim()
  if (!email) errors.push('E-mail é obrigatório.')
  else if (!EMAIL_RE.test(email)) errors.push('E-mail inválido.')
  if (!isEdit) {
    if (!(draft.first_name ?? '').trim()) errors.push('Nome é obrigatório.')
    if (!(draft.last_name ?? '').trim()) errors.push('Sobrenome é obrigatório.')
    if (!(draft.password ?? '').trim()) errors.push('Senha é obrigatória.')
  }
  return errors
}

/**
 * Corpo de criação (POST). Só aqui a senha existe.
 */
export function buildCreatePayload(draft: TenantUserDraft): Record<string, unknown> {
  const opt = (v: string) => (v.trim() ? v.trim() : undefined)
  return {
    email: draft.email.trim(),
    first_name: draft.first_name.trim(),
    last_name: draft.last_name.trim(),
    password: draft.password,
    role: draft.role,
    phone: opt(draft.phone),
    mobile: opt(draft.mobile),
    extension: opt(draft.extension),
    active: draft.active,
    email_intake_enabled: draft.email_intake_enabled,
  }
}

/**
 * Corpo de edição (PUT). NUNCA carrega senha — trocar senha é operação
 * separada e explícita, e o Perl rejeita qualquer chave com cara de senha.
 * Um payload de edição que levasse `password` viraria 4xx do Znuny, então
 * mantê-lo fora daqui é correção, não só higiene.
 */
export function buildUpdatePayload(draft: TenantUserDraft): Record<string, unknown> {
  return {
    first_name: draft.first_name.trim(),
    last_name: draft.last_name.trim(),
    email: draft.email.trim(),
    phone: draft.phone.trim(),
    mobile: draft.mobile.trim(),
    extension: draft.extension.trim() || null,
    active: draft.active,
    role: draft.role,
    email_intake_enabled: draft.email_intake_enabled,
  }
}

/**
 * Desativar é ação de risco (a pessoa perde o portal): exige digitar o e-mail,
 * igual às outras confirmações destrutivas do console. Comparação sem caixa e
 * sem espaço nas pontas — o operador copia e cola.
 */
export function confirmDeactivateMatches(typed: string, login: string): boolean {
  return typed.trim().toLowerCase() === login.trim().toLowerCase()
}

/** Rótulo do estado da pessoa, para a tabela. */
export function userStatusLabel(u: TenantUser): string {
  if (!u.active) return 'Inativo'
  if (!u.has_portal_access) return 'Sem acesso ao portal'
  return 'Ativo'
}
