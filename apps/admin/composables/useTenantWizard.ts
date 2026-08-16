// Assistente de cadastro de cliente em 3 etapas (T-R1.4, R1 do vídeo do Kleber).
//
// *"Ele tem um passo a passo de cadastro do cliente […] e ao final do cadastro
// do cliente, ele vai me levar pra uma telinha de edição"* (01:10).
//
// Hoje é um formulão de página única: o operador só descobre que errou o CNPJ
// depois de preencher branding e usuários. O assistente valida POR ETAPA, e
// "Avançar" não passa enquanto a etapa não estiver boa.
//
// Lógica PURA (sem Nuxt/DOM), testável isoladamente. A verdade continua sendo
// o 4xx do sidecar — isto é feedback imediato, não substituto de validação.

export type WizardStep = 1 | 2 | 3

export interface TenantUserDraft {
  email: string
  first_name: string
  last_name: string
  password: string
  role: 'admin' | 'helpdesk'
  phone: string
  extension: string
  email_intake_enabled: boolean
}

export interface TenantWizardDraft {
  // Etapa 1 — dados cadastrais, endereço e contato
  legal_name: string
  trade_name: string
  document: string
  subdomain: string
  znuny_customer_id: string
  address_street: string
  address_number: string
  address_complement: string
  address_district: string
  address_city: string
  address_state: string
  address_zip: string
  contact_name: string
  contact_email: string
  contact_phone: string
  // Etapa 2 — identidade visual
  display_name: string
  primary_color: string
  accent_color: string
  support_email: string
  logo_url: string
  // Etapa 3 — pessoas
  users: TenantUserDraft[]
}

export const STEP_TITLES: Record<WizardStep, string> = {
  1: 'Dados cadastrais',
  2: 'Identidade visual',
  3: 'Usuários',
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
// Subdomínio vira hostname: só minúsculas, dígitos e hífen no meio.
const SUBDOMAIN_RE = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/

export function emptyTenantUser(role: 'admin' | 'helpdesk' = 'helpdesk'): TenantUserDraft {
  return {
    email: '',
    first_name: '',
    last_name: '',
    password: '',
    role,
    phone: '',
    extension: '',
    email_intake_enabled: true,
  }
}

export function emptyTenantWizardDraft(): TenantWizardDraft {
  return {
    legal_name: '',
    trade_name: '',
    document: '',
    subdomain: '',
    znuny_customer_id: '',
    address_street: '',
    address_number: '',
    address_complement: '',
    address_district: '',
    address_city: '',
    address_state: '',
    address_zip: '',
    contact_name: '',
    contact_email: '',
    contact_phone: '',
    display_name: '',
    primary_color: '#2563EB',
    accent_color: '#1E40AF',
    support_email: '',
    logo_url: '',
    users: [emptyTenantUser('admin')],
  }
}

/** CEP guardado só com dígitos — o operador digita com ponto e traço. */
export function normalizeZip(value: string): string {
  return value.replace(/\D/g, '').slice(0, 8)
}

/** UF em maiúsculas, no máximo 2 letras. */
export function normalizeState(value: string): string {
  return value.replace(/[^A-Za-z]/g, '').toUpperCase().slice(0, 2)
}

/**
 * Erros da etapa, em português e na ordem em que os campos aparecem na tela.
 * Lista vazia = etapa válida.
 */
export function validateStep(step: WizardStep, draft: TenantWizardDraft): string[] {
  const errors: string[] = []
  if (step === 1) {
    if (!draft.legal_name.trim()) errors.push('Razão social é obrigatória.')
    if (!draft.trade_name.trim()) errors.push('Nome fantasia é obrigatório.')
    if (!draft.document.trim()) errors.push('CNPJ/documento é obrigatório.')
    const sub = draft.subdomain.trim()
    if (!sub) errors.push('Subdomínio é obrigatório.')
    else if (!SUBDOMAIN_RE.test(sub)) {
      errors.push('Subdomínio aceita só letras minúsculas, números e hífen.')
    }
    if (!draft.znuny_customer_id.trim()) errors.push('ID do cliente no Znuny é obrigatório.')
    // Endereço e contato são opcionais no cadastro — mas o que for preenchido
    // precisa fazer sentido, senão o erro só aparece na tela de edição depois.
    const zip = normalizeZip(draft.address_zip)
    if (draft.address_zip.trim() && zip.length !== 8) errors.push('CEP deve ter 8 dígitos.')
    const contactEmail = draft.contact_email.trim()
    if (contactEmail && !EMAIL_RE.test(contactEmail)) {
      errors.push('E-mail de contato inválido.')
    }
  }
  if (step === 2) {
    if (!draft.display_name.trim()) errors.push('Nome de exibição é obrigatório.')
    const support = draft.support_email.trim()
    if (support && !EMAIL_RE.test(support)) errors.push('E-mail de suporte inválido.')
    const logo = draft.logo_url.trim()
    if (logo && !logo.startsWith('https://')) errors.push('URL do logo precisa ser https://.')
  }
  if (step === 3) {
    if (draft.users.length === 0) errors.push('Cadastre ao menos um usuário.')
    draft.users.forEach((u, i) => {
      const n = i + 1
      if (!u.email.trim()) errors.push(`Usuário ${n}: e-mail é obrigatório.`)
      else if (!EMAIL_RE.test(u.email.trim())) errors.push(`Usuário ${n}: e-mail inválido.`)
      if (!u.first_name.trim()) errors.push(`Usuário ${n}: nome é obrigatório.`)
      if (!u.last_name.trim()) errors.push(`Usuário ${n}: sobrenome é obrigatório.`)
      if (!u.password.trim()) errors.push(`Usuário ${n}: senha é obrigatória.`)
    })
    const seen = new Set<string>()
    for (const u of draft.users) {
      const key = u.email.trim().toLowerCase()
      if (!key) continue
      if (seen.has(key)) errors.push(`E-mail repetido: ${key}.`)
      seen.add(key)
    }
  }
  return errors
}

export function canAdvance(step: WizardStep, draft: TenantWizardDraft): boolean {
  return validateStep(step, draft).length === 0
}

/**
 * Corpo do POST. Idêntico ao de antes da Onda 1, mais os campos novos —
 * o contrato antigo não muda, o assistente só ganhou etapas.
 *
 * Campo opcional vazio vai como `undefined` (ausente), nunca como string
 * vazia: no PUT de edição isso é a diferença entre "não mexi" e "apaguei".
 */
export function buildTenantBody(draft: TenantWizardDraft): Record<string, unknown> {
  const opt = (v: string) => (v.trim() ? v.trim() : undefined)
  return {
    legal_name: draft.legal_name.trim(),
    trade_name: draft.trade_name.trim(),
    document: draft.document.trim(),
    subdomain: draft.subdomain.trim(),
    znuny_customer_id: draft.znuny_customer_id.trim(),
    address_street: opt(draft.address_street),
    address_number: opt(draft.address_number),
    address_complement: opt(draft.address_complement),
    address_district: opt(draft.address_district),
    address_city: opt(draft.address_city),
    address_state: opt(normalizeState(draft.address_state)),
    address_zip: opt(normalizeZip(draft.address_zip)),
    contact_name: opt(draft.contact_name),
    contact_email: opt(draft.contact_email),
    contact_phone: opt(draft.contact_phone),
    branding: {
      display_name: draft.display_name.trim(),
      primary_color: draft.primary_color,
      accent_color: draft.accent_color,
      support_email: opt(draft.support_email),
      logo_url: opt(draft.logo_url),
    },
    users: draft.users.map(u => ({
      email: u.email.trim(),
      first_name: u.first_name.trim(),
      last_name: u.last_name.trim(),
      password: u.password,
      role: u.role,
      phone: opt(u.phone),
      extension: opt(u.extension),
      email_intake_enabled: u.email_intake_enabled,
    })),
  }
}
