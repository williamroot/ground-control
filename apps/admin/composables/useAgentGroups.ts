// Agentes e permissões do Znuny (Spec #4, Bloco C) — lógica PURA do
// formulário de cadastro e do diff de grupos/papéis. Sem Nuxt/DOM: testável
// isoladamente (vitest). O diff é o que a tela de confirmação mostra antes de
// qualquer PUT de permissão — é a ação mais perigosa desta spec.
//
// Contrato consumido (sidecar — `docs/superpowers/plans/
// 2026-07-30-spec-4-capa-admin-znuny.md`):
//   GET  /api/admin/znuny/agents                 -> { items: AgentRow[] }  (nunca traz UserPw)
//   GET  /api/admin/znuny/agents/{id}             -> AgentRow
//   POST /api/admin/znuny/agents                  body: cadastro (sem senha)
//   PUT  /api/admin/znuny/agents/{id}              body: cadastro — NUNCA carrega senha
//   POST /api/admin/znuny/agents/{id}/password     body: { new_password } — operação SEPARADA e explícita
//   GET  /api/admin/znuny/groups                  -> { items: GroupRow[] }
//   PUT  /api/admin/znuny/agents/{id}/groups       body: { GroupIDs: string[] } — audita antes/depois
// Definir senha é sempre uma chamada separada, com payload que só carrega
// `new_password` — nunca um efeito colateral de salvar o cadastro (correção
// pós-revisão adversarial: o endpoint antigo, PUT com `NewPassword`, nunca
// existiu de verdade no backend — o botão sempre respondia 422).

export interface AgentRow {
  UserID: string | number
  UserLogin: string
  UserFirstname: string
  UserLastname: string
  UserEmail: string
  ValidID: string | number
}

export interface GroupRow {
  GroupID: string | number
  Name: string
  ValidID?: string | number
}

export function agentValidLabel(validId: string | number | null | undefined): string {
  switch (String(validId ?? '')) {
    case '1': return 'válido'
    case '2': return 'inválido'
    case '3': return 'inválido temporariamente'
    default: return 'desconhecido'
  }
}

// Nome distinto de `useCiDefinition.ts` (ambos exportam esse alias e o Nuxt
// auto-import global colidiria se os dois se chamassem `SemanticColor`).
export type AgentSemanticColor = 'success' | 'error' | 'warning' | 'neutral'

export function agentValidColor(validId: string | number | null | undefined): AgentSemanticColor {
  switch (String(validId ?? '')) {
    case '1': return 'success'
    case '2': return 'error'
    case '3': return 'warning'
    default: return 'neutral'
  }
}

export function agentFullName(row: Pick<AgentRow, 'UserFirstname' | 'UserLastname'>): string {
  return `${row.UserFirstname} ${row.UserLastname}`.trim()
}

// --- Cadastro (perfil) -------------------------------------------------------

export interface AgentProfileDraft {
  UserLogin: string
  UserFirstname: string
  UserLastname: string
  UserEmail: string
  ValidID: string
}

export function emptyAgentDraft(): AgentProfileDraft {
  return { UserLogin: '', UserFirstname: '', UserLastname: '', UserEmail: '', ValidID: '1' }
}

export function agentDraftFromRow(row: AgentRow): AgentProfileDraft {
  return {
    UserLogin: row.UserLogin,
    UserFirstname: row.UserFirstname,
    UserLastname: row.UserLastname,
    UserEmail: row.UserEmail,
    ValidID: String(row.ValidID),
  }
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** Validação leve (espelho do 422 do sidecar, que é a fonte de verdade). NUNCA valida senha aqui — cadastro não carrega senha. */
export function validateAgentProfile(draft: AgentProfileDraft, isNew: boolean): string[] {
  const errors: string[] = []
  if (isNew) {
    const login = draft.UserLogin.trim()
    if (login.length < 3) errors.push('Login deve ter ao menos 3 caracteres.')
    if (/\s/.test(login)) errors.push('Login não pode conter espaços.')
  }
  if (!draft.UserFirstname.trim()) errors.push('Nome é obrigatório.')
  if (!draft.UserLastname.trim()) errors.push('Sobrenome é obrigatório.')
  if (!EMAIL_RE.test(draft.UserEmail.trim())) errors.push('E-mail inválido.')
  if (!draft.ValidID) errors.push('Validade é obrigatória.')
  return errors
}

export function isAgentProfileValid(draft: AgentProfileDraft, isNew: boolean): boolean {
  return validateAgentProfile(draft, isNew).length === 0
}

export interface AgentProfilePayload {
  UserLogin?: string
  UserFirstname: string
  UserLastname: string
  UserEmail: string
  ValidID: string
}

/** Payload do cadastro — NUNCA carrega senha (definir senha é ação separada). */
export function buildAgentProfilePayload(draft: AgentProfileDraft, isNew: boolean): AgentProfilePayload {
  return {
    ...(isNew ? { UserLogin: draft.UserLogin.trim() } : {}),
    UserFirstname: draft.UserFirstname.trim(),
    UserLastname: draft.UserLastname.trim(),
    UserEmail: draft.UserEmail.trim(),
    ValidID: draft.ValidID,
  }
}

interface SidecarErrorLike {
  statusCode?: number
  data?: { detail?: string }
}

export function extractAgentError(err: unknown): string {
  const e = err as SidecarErrorLike
  const detail = e?.data?.detail
  if (detail && detail.trim()) return detail
  return 'Falha ao salvar o agente. Tente novamente.'
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

function toIdSet(ids: (string | number)[]): Set<string> {
  return new Set(ids.map(String))
}

/**
 * Diff do que muda ao trocar a lista de grupos do agente. É isso que a tela
 * de confirmação mostra ("vai ganhar X, vai perder Y") antes do PUT — a
 * confirmação é obrigatória nesta spec porque é a ação mais perigosa.
 */
export function diffAgentGroups(
  currentIds: (string | number)[],
  nextIds: (string | number)[],
  groups: GroupRow[],
): GroupDiff {
  const current = toIdSet(currentIds)
  const next = toIdSet(nextIds)
  const byId = new Map(groups.map(g => [String(g.GroupID), g]))
  const sortByName = (a: GroupRow, b: GroupRow) => a.Name.localeCompare(b.Name, 'pt-BR')

  const gained: GroupRow[] = []
  const lost: GroupRow[] = []
  const unchanged: GroupRow[] = []

  for (const id of new Set([...current, ...next])) {
    const group = byId.get(id) ?? { GroupID: id, Name: id }
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

export const ADMIN_GROUP_NAME = 'admin'

/**
 * Guarda client-side (proativa) contra o anti-lockout: o próprio agente
 * logado tentando remover a si mesmo do grupo `admin`. O sidecar recusa isso
 * de verdade (422) — este check só evita mandar uma requisição fadada ao
 * fracasso e explica o motivo antes de tentar.
 */
export function wouldRemoveSelfFromAdmin(
  isSelf: boolean,
  diff: GroupDiff,
  adminGroupName: string = ADMIN_GROUP_NAME,
): boolean {
  if (!isSelf) return false
  return diff.lost.some(g => g.Name.toLowerCase() === adminGroupName.toLowerCase())
}

export function buildGroupsPayload(nextIds: (string | number)[]): { GroupIDs: string[] } {
  return { GroupIDs: nextIds.map(String) }
}

const LOCKOUT_FALLBACK
  = 'O Znuny recusou: um agente não pode remover a si mesmo do grupo administrador (trava contra lockout do console).'

/** Mensagem amigável para o 422 de grupos — inclusive o anti-lockout, tratado em vez de mostrado cru. */
export function extractGroupsError(err: unknown, selfLockoutAttempt: boolean): string {
  const e = err as SidecarErrorLike
  const detail = e?.data?.detail
  if (e?.statusCode === 422 && selfLockoutAttempt) return LOCKOUT_FALLBACK
  if (detail && detail.trim()) return detail
  return 'Falha ao salvar as permissões. Tente novamente.'
}
