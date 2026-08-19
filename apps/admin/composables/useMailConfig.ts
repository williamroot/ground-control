// Configuração de e-mail do Znuny (T-R9.7, R9 do vídeo). Lógica PURA.
//
// *"Se entrou pelo suporte, tem que sair pelo suporte. Se entrou pelo
// financeiro, tem que sair pelo financeiro."* (06:38)
//
// A tela junta três coisas que no Znuny nativo moram em telas separadas, e é
// essa junção que responde à pergunta do Kleber numa olhada:
//
//   entrada  → conta de recebimento, amarrada a uma fila
//   saída    → endereço de sistema da fila (SystemAddressID)
//   domínio  → filtro de PostMaster: qual domínio é de qual cliente
//
// **A ressalva do A9.6 vive aqui**, em `outboundWarning`: a amarração de saída
// é pela fila ATUAL do chamado, não pela porta de entrada. No fluxo que o
// próprio Kleber descreve — tudo cai na fila padrão e o N1 move — a resposta
// passa a sair pelo endereço da fila de DESTINO. Não é defeito, é o desenho do
// Znuny, e ele precisa saber disso antes de aceitar o requisito.

export type MailAccountType = 'POP3' | 'POP3S' | 'POP3TLS' | 'IMAP' | 'IMAPS' | 'IMAPTLS'
export type DispatchingBy = 'Queue' | 'From'

export const MAIL_ACCOUNT_TYPES: MailAccountType[] = [
  'IMAPS', 'IMAPTLS', 'IMAP', 'POP3S', 'POP3TLS', 'POP3',
]

export interface MailAccount {
  id: number
  login: string
  host: string
  type: MailAccountType
  valid: boolean
  trusted: boolean
  dispatching_by: DispatchingBy
  queue_id: number
  queue_name: string
  comment: string
  imap_folder: string
  has_password: boolean
}

export interface MailAccountDraft {
  id: number | null
  login: string
  host: string
  type: MailAccountType
  password: string
  valid: boolean
  trusted: boolean
  dispatching_by: DispatchingBy
  queue_id: number
  comment: string
  imap_folder: string
}

export interface FilterPair { key: string, value: string }

export interface PostMasterFilter {
  name: string
  stop_after_match: boolean
  match: FilterPair[]
  set: FilterPair[]
}

export interface DomainRuleDraft {
  name: string
  domain: string
  customer_id: string
  queue_name: string
  stop_after_match: boolean
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
// Domínio puro: sem arroba, sem barra, com pelo menos um ponto.
const DOMAIN_RE = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$/
const FILTER_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9 ._:-]{0,63}$/

export function emptyMailAccountDraft(): MailAccountDraft {
  return {
    id: null,
    login: '',
    host: '',
    type: 'IMAPS',
    password: '',
    valid: true,
    trusted: false,
    dispatching_by: 'Queue',
    queue_id: 0,
    comment: '',
    imap_folder: 'INBOX',
  }
}

export function draftFromAccount(a: MailAccount): MailAccountDraft {
  return {
    id: a.id,
    login: a.login,
    host: a.host,
    type: a.type,
    password: '', // NUNCA pré-preenchido: o servidor não devolve senha
    valid: a.valid,
    trusted: a.trusted,
    dispatching_by: a.dispatching_by,
    queue_id: a.queue_id,
    comment: a.comment,
    imap_folder: a.imap_folder,
  }
}

/** Erros em português. Lista vazia = pode salvar. */
export function validateMailAccount(draft: MailAccountDraft): string[] {
  const errors: string[] = []
  const isNew = draft.id === null
  if (!draft.login.trim()) errors.push('Usuário da caixa é obrigatório.')
  if (!draft.host.trim()) errors.push('Servidor é obrigatório.')
  if (isNew && !draft.password.trim()) {
    errors.push('Senha é obrigatória ao cadastrar uma caixa nova.')
  }
  if (draft.dispatching_by === 'Queue' && !draft.queue_id) {
    // Sem fila, a mensagem entra e não se sabe onde ela cai — é o oposto do
    // "quando enviar para esse e-mail, vai para a fila X" (05:57).
    errors.push('Escolha a fila que vai receber as mensagens desta caixa.')
  }
  return errors
}

/**
 * Corpo do POST/PUT. `password` só vai quando o operador digitou algo — é o
 * que permite editar a fila de uma caixa sem o console jamais ter conhecido a
 * senha dela.
 */
export function buildMailAccountPayload(draft: MailAccountDraft): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    login: draft.login.trim(),
    host: draft.host.trim(),
    type: draft.type,
    valid: draft.valid,
    trusted: draft.trusted,
    dispatching_by: draft.dispatching_by,
    queue_id: draft.queue_id,
    comment: draft.comment.trim(),
    imap_folder: draft.imap_folder.trim(),
  }
  if (draft.password.trim()) payload.password = draft.password
  return payload
}

/** O que a tela mostra no campo de senha de uma conta que já existe. */
export function passwordPlaceholder(draft: MailAccountDraft): string {
  return draft.id === null ? 'Senha da caixa' : '•••• (mantida — digite para trocar)'
}

// ── domínios autorizados ────────────────────────────────────────────────────

/** Extrai o domínio de um filtro cujo `Match` é `From =~ @dominio`. */
export function domainOfFilter(f: PostMasterFilter): string | null {
  const from = f.match.find(p => p.key.toLowerCase() === 'from')
  if (!from) return null
  const m = /@([a-z0-9.-]+)/i.exec(from.value)
  return m ? m[1]!.toLowerCase() : from.value
}

/** O cliente que o filtro atribui, se atribuir. */
export function customerOfFilter(f: PostMasterFilter): string | null {
  return f.set.find(p => p.key === 'X-OTRS-CustomerNo')?.value ?? null
}

export function validateDomainRule(draft: DomainRuleDraft): string[] {
  const errors: string[] = []
  if (!FILTER_NAME_RE.test(draft.name.trim())) {
    errors.push('Nome da regra aceita letras, números, espaço, ponto, hífen e dois-pontos.')
  }
  const domain = draft.domain.trim().replace(/^@/, '').toLowerCase()
  if (!domain) errors.push('Domínio é obrigatório.')
  else if (EMAIL_RE.test(domain)) errors.push('Informe o domínio, não um e-mail completo.')
  else if (!DOMAIN_RE.test(domain)) errors.push('Domínio inválido (ex.: cliente.com.br).')
  if (!draft.customer_id.trim()) errors.push('Escolha o cliente dono deste domínio.')
  return errors
}

/**
 * Monta o filtro de PostMaster a partir do que o operador descreveu.
 *
 * O regex escapa o ponto: `@cliente.com.br` sem escape casaria também
 * `@clienteXcomYbr`, e um domínio parecido cairia como sendo do cliente errado.
 */
export function buildDomainRulePayload(draft: DomainRuleDraft): Record<string, unknown> {
  const domain = draft.domain.trim().replace(/^@/, '').toLowerCase()
  const escaped = domain.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const set: FilterPair[] = [
    { key: 'X-OTRS-CustomerNo', value: draft.customer_id.trim() },
  ]
  if (draft.queue_name.trim()) {
    set.push({ key: 'X-OTRS-Queue', value: draft.queue_name.trim() })
  }
  return {
    name: draft.name.trim(),
    match: [{ key: 'From', value: `@${escaped}$` }],
    set,
    stop_after_match: draft.stop_after_match,
  }
}

/**
 * A ressalva do aceite A9.6, em texto, para a tela mostrar sem que ninguém
 * precise lembrar de contá-la numa demonstração.
 */
export const OUTBOUND_WARNING
  = 'O endereço de resposta é o da fila ONDE O CHAMADO ESTÁ, não o da caixa por onde '
    + 'ele entrou. Se o N1 move o chamado para outra fila, a resposta passa a sair pelo '
    + 'endereço dessa fila. É comportamento nativo do Znuny.'
