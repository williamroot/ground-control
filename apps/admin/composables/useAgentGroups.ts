// Agentes e permissões do Znuny (Spec #4, Bloco C) — lógica PURA do
// formulário de cadastro e do diff de grupos/papéis. Sem Nuxt/DOM: testável
// isoladamente (vitest). O diff é o que a tela de confirmação mostra antes de
// qualquer PUT de permissão — é a ação mais perigosa desta spec.
//
// Contrato REAL do sidecar (`apps/sidecar/src/gerti_sidecar/routers/
// admin_znuny_people.py`). A versão anterior desta tela falava o formato do
// Znuny (`{ items: [{ UserLogin, ValidID }] }`), que o sidecar nunca devolveu:
// em staging a lista vinha vazia ("Nenhum agente cadastrado") com 5 agentes
// válidos no Znuny (teste V01).
//   GET  /api/admin/znuny/agents               -> AgentRow[]  (lista pura, sem `items`, nunca traz senha)
//   GET  /api/admin/znuny/agents/{id}          -> AgentRow    (SEM grupos — ver abaixo)
//   POST /api/admin/znuny/agents               body: { login, first_name, last_name, email, valid }
//   PUT  /api/admin/znuny/agents/{id}          body: { first_name, last_name, email, valid } — NUNCA senha
//   POST /api/admin/znuny/agents/{id}/password body: { new_password } — operação SEPARADA e explícita
//   GET  /api/admin/znuny/groups               -> GroupRow[]
//   PUT  /api/admin/znuny/agents/{id}/groups   body: { group_ids, permissions? }
//                                              -> { agent_id, before: [{id,name}], after: [{id,name}] }
//
// O sidecar NÃO tem leitura dos grupos atuais de um agente, e o PUT de grupos
// SUBSTITUI a lista inteira. Então: grupos atuais são "desconhecidos" até a
// primeira gravação nesta sessão (aí o `after` da resposta vira o estado
// conhecido), e a tela avisa que salvar troca tudo pelo que está marcado.

export interface AgentRow {
  id: number
  login: string
  first_name: string
  last_name: string
  email: string
  valid: boolean
}

export interface GroupRow {
  id: number
  name: string
  comment?: string
  valid?: boolean
  rw_user_count?: number | null
}

export interface GroupMembership { id: number, name: string }

export interface AgentGroupsChange {
  agent_id: number
  before: GroupMembership[]
  after: GroupMembership[]
}

function text(v: unknown): string {
  return typeof v === 'string' ? v : ''
}

function intId(v: unknown): number | null {
  const n = typeof v === 'number' ? v : typeof v === 'string' && /^\d+$/.test(v) ? Number(v) : Number.NaN
  return Number.isInteger(n) && n > 0 ? n : null
}

/**
 * Lista de agentes do sidecar -> linhas da tabela. `null` quando a resposta
 * não é uma lista (falha do proxy, forma inesperada): a tela mostra ERRO, não
 * "nenhum agente" — confundir os dois foi exatamente o defeito do teste V01.
 */
export function parseAgentList(raw: unknown): AgentRow[] | null {
  if (!Array.isArray(raw)) return null
  const out: AgentRow[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const a = item as Record<string, unknown>
    const id = intId(a.id)
    const login = text(a.login).trim()
    if (id === null || !login) continue
    out.push({
      id,
      login,
      first_name: text(a.first_name),
      last_name: text(a.last_name),
      email: text(a.email),
      valid: a.valid === true,
    })
  }
  return out.sort((x, y) => x.login.localeCompare(y.login, 'pt-BR'))
}

/** Lista de grupos do sidecar, ordenada por nome. Resposta inválida -> []. */
export function parseGroupList(raw: unknown): GroupRow[] {
  if (!Array.isArray(raw)) return []
  const out: GroupRow[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const g = item as Record<string, unknown>
    const id = intId(g.id)
    const name = text(g.name).trim()
    if (id === null || !name) continue
    out.push({
      id,
      name,
      comment: text(g.comment),
      valid: g.valid !== false,
      rw_user_count: typeof g.rw_user_count === 'number' ? g.rw_user_count : null,
    })
  }
  return out.sort((x, y) => x.name.localeCompare(y.name, 'pt-BR'))
}

export function agentValidLabel(valid: boolean | null | undefined): string {
  if (valid === true) return 'válido'
  if (valid === false) return 'inválido'
  return 'desconhecido'
}

// Nome distinto de `useCiDefinition.ts` (ambos exportam esse alias e o Nuxt
// auto-import global colidiria se os dois se chamassem `SemanticColor`).
export type AgentSemanticColor = 'success' | 'error' | 'warning' | 'neutral'

export function agentValidColor(valid: boolean | null | undefined): AgentSemanticColor {
  if (valid === true) return 'success'
  if (valid === false) return 'error'
  return 'neutral'
}

export function agentFullName(row: Pick<AgentRow, 'first_name' | 'last_name'>): string {
  return `${row.first_name} ${row.last_name}`.trim()
}

// --- Cadastro (perfil) -------------------------------------------------------

/** Rascunho do formulário. `valid` é string porque é o valor do USelect. */
export interface AgentProfileDraft {
  login: string
  first_name: string
  last_name: string
  email: string
  valid: 'true' | 'false'
}

export function emptyAgentDraft(): AgentProfileDraft {
  return { login: '', first_name: '', last_name: '', email: '', valid: 'true' }
}

export function agentDraftFromRow(row: AgentRow): AgentProfileDraft {
  return {
    login: row.login,
    first_name: row.first_name,
    last_name: row.last_name,
    email: row.email,
    valid: row.valid ? 'true' : 'false',
  }
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** Validação leve (espelho do 422 do sidecar, que é a fonte de verdade). NUNCA valida senha aqui — cadastro não carrega senha. */
export function validateAgentProfile(draft: AgentProfileDraft, isNew: boolean): string[] {
  const errors: string[] = []
  if (isNew) {
    const login = draft.login.trim()
    if (login.length < 3) errors.push('Login deve ter ao menos 3 caracteres.')
    if (/\s/.test(login)) errors.push('Login não pode conter espaços.')
  }
  if (!draft.first_name.trim()) errors.push('Nome é obrigatório.')
  if (!draft.last_name.trim()) errors.push('Sobrenome é obrigatório.')
  if (!EMAIL_RE.test(draft.email.trim())) errors.push('E-mail inválido.')
  if (draft.valid !== 'true' && draft.valid !== 'false') errors.push('Validade é obrigatória.')
  return errors
}

export function isAgentProfileValid(draft: AgentProfileDraft, isNew: boolean): boolean {
  return validateAgentProfile(draft, isNew).length === 0
}

export interface AgentProfilePayload {
  login?: string
  first_name: string
  last_name: string
  email: string
  valid: boolean
}

/**
 * Corpo do POST (com `login`) ou do PUT (sem: o login é imutável e o
 * `AgentUpdate` do sidecar nem tem o campo). NUNCA carrega senha.
 */
export function buildAgentProfilePayload(draft: AgentProfileDraft, isNew: boolean): AgentProfilePayload {
  return {
    ...(isNew ? { login: draft.login.trim() } : {}),
    first_name: draft.first_name.trim(),
    last_name: draft.last_name.trim(),
    email: draft.email.trim(),
    valid: draft.valid === 'true',
  }
}

interface SidecarErrorLike {
  statusCode?: number
  data?: { detail?: unknown }
}

/** `detail` em português quando o sidecar manda código (`znuny_unavailable`). */
function detailMessage(err: unknown): string {
  const detail = (err as SidecarErrorLike | null)?.data?.detail
  if (detail === 'znuny_unavailable') return 'O Znuny está indisponível no momento. Tente novamente em instantes.'
  if (detail === 'agent_not_found') return 'Agente não encontrado no Znuny.'
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const msgs = detail
      .map(d => (d && typeof d === 'object' ? text((d as { msg?: unknown }).msg) : ''))
      .filter(Boolean)
    if (msgs.length) return msgs.join(' ')
  }
  return ''
}

export function extractAgentError(err: unknown): string {
  return detailMessage(err) || 'Falha ao salvar o agente. Tente novamente.'
}

// --- Senha (ação separada e explícita) ---------------------------------------

const MIN_PASSWORD_LENGTH = 10

export function validatePassword(password: string, confirmation: string): string[] {
  const errors: string[] = []
  if (password.length < MIN_PASSWORD_LENGTH) {
    errors.push(`A senha deve ter ao menos ${MIN_PASSWORD_LENGTH} caracteres.`)
  }
  if (password !== confirmation) errors.push('As senhas não coincidem.')
  return errors
}

export function isPasswordValid(password: string, confirmation: string): boolean {
  return validatePassword(password, confirmation).length === 0
}

/** Payload da troca de senha — SÓ a senha, nunca junto de outros campos de cadastro. */
export function buildPasswordPayload(password: string): { new_password: string } {
  return { new_password: password }
}

// --- Grupos/papéis: diff de permissões ---------------------------------------

export interface GroupDiff {
  gained: GroupRow[]
  lost: GroupRow[]
  unchanged: GroupRow[]
}

function toIdSet(ids: (string | number)[]): Set<number> {
  return new Set(ids.map(Number).filter(n => Number.isInteger(n) && n > 0))
}

/**
 * Diff do que muda ao trocar a lista de grupos do agente — só existe quando os
 * grupos atuais são CONHECIDOS (gravados nesta sessão). Grupo fora da lista de
 * apoio aparece pelo id, para nunca sumir da confirmação.
 */
export function diffAgentGroups(
  currentIds: (string | number)[],
  nextIds: (string | number)[],
  groups: GroupRow[],
): GroupDiff {
  const current = toIdSet(currentIds)
  const next = toIdSet(nextIds)
  const byId = new Map(groups.map(g => [g.id, g]))
  const sortByName = (a: GroupRow, b: GroupRow) => a.name.localeCompare(b.name, 'pt-BR')

  const gained: GroupRow[] = []
  const lost: GroupRow[] = []
  const unchanged: GroupRow[] = []

  for (const id of new Set([...current, ...next])) {
    const group = byId.get(id) ?? { id, name: `#${id}` }
    const wasIn = current.has(id)
    const willBeIn = next.has(id)
    if (wasIn && !willBeIn) lost.push(group)
    else if (!wasIn && willBeIn) gained.push(group)
    else if (wasIn && willBeIn) unchanged.push(group)
  }

  return { gained: gained.sort(sortByName), lost: lost.sort(sortByName), unchanged: unchanged.sort(sortByName) }
}

export function hasGroupChanges(diff: GroupDiff): boolean {
  return diff.gained.length > 0 || diff.lost.length > 0
}

/** Grupos marcados, com nome, ordenados — o "vai ficar com" da confirmação. */
export function selectedGroups(nextIds: (string | number)[], groups: GroupRow[]): GroupRow[] {
  return diffAgentGroups([], nextIds, groups).gained
}

/**
 * Seleção vazia não é enviada: como o PUT substitui a lista inteira, ela
 * tiraria TODO acesso do agente. Para desligar alguém, o caminho é marcar o
 * cadastro como inválido.
 */
export function validateGroupSelection(nextIds: (string | number)[]): string[] {
  if (toIdSet(nextIds).size === 0) {
    return ['Marque ao menos um grupo. Para desligar o agente, marque o cadastro como inválido.']
  }
  return []
}

export const ADMIN_GROUP_NAME = 'admin'

/**
 * Guarda client-side (proativa) contra o anti-lockout: o próprio agente
 * logado ficando sem o grupo `admin`. Com os grupos atuais DESCONHECIDOS
 * (`currentIds === null`) a regra é conservadora: basta o `admin` não estar
 * marcado — não dá para saber se ele "já não tinha". O sidecar recusa de
 * verdade (422); isto só evita a requisição fadada ao fracasso.
 */
export function wouldRemoveSelfFromAdmin(
  isSelf: boolean,
  currentIds: (string | number)[] | null,
  nextIds: (string | number)[],
  groups: GroupRow[],
  adminGroupName: string = ADMIN_GROUP_NAME,
): boolean {
  if (!isSelf) return false
  const admin = groups.find(g => g.name.toLowerCase() === adminGroupName.toLowerCase())
  if (!admin) return false
  const keeps = toIdSet(nextIds).has(admin.id)
  if (keeps) return false
  return currentIds === null ? true : toIdSet(currentIds).has(admin.id)
}

/** Corpo do PUT de grupos: ids inteiros, sem repetição, ordenados. Sem `permissions` = `rw` em cada grupo. */
export function buildGroupsPayload(nextIds: (string | number)[]): { group_ids: number[] } {
  return { group_ids: [...toIdSet(nextIds)].sort((a, b) => a - b) }
}

/** Ids do `after` da resposta do PUT — vira o estado conhecido do agente. */
export function groupIdsFromChange(change: unknown): number[] | null {
  const after = (change as { after?: unknown } | null)?.after
  if (!Array.isArray(after)) return null
  return after.map(m => intId((m as { id?: unknown } | null)?.id)).filter((n): n is number => n !== null)
}

/** "admin, users → suporte" para o aviso de sucesso (o que o Znuny tinha e o que ficou). */
export function describeGroupsChange(change: unknown): string {
  const c = change as Partial<AgentGroupsChange> | null
  const names = (rows: unknown) => (Array.isArray(rows)
    ? rows.map(r => text((r as { name?: unknown } | null)?.name)).filter(Boolean).join(', ')
    : '')
  const before = names(c?.before) || 'nenhum grupo'
  const after = names(c?.after) || 'nenhum grupo'
  return `Antes: ${before}. Agora: ${after}.`
}

const LOCKOUT_FALLBACK
  = 'O Znuny recusou: um agente não pode remover a si mesmo do grupo administrador (trava contra lockout do console).'

/** Mensagem amigável para o 422 de grupos — inclusive o anti-lockout, tratado em vez de mostrado cru. */
export function extractGroupsError(err: unknown, selfLockoutAttempt: boolean): string {
  const e = err as SidecarErrorLike
  if (e?.statusCode === 422 && selfLockoutAttempt) return LOCKOUT_FALLBACK
  return detailMessage(err) || 'Falha ao salvar as permissões. Tente novamente.'
}
