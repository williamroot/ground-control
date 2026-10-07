// R16 — regras da tela de licenciamento. Lógica PURA.
//
// *"Hoje tem sete usuários ativos, a gente tem um total de nove. […] Isso aqui
// impacta no faturamento da plataforma para a gente."* (09:24)
//
// A verdade é o 422 do sidecar. O que está aqui existe para o operador não
// gastar um round-trip descobrindo que não tem seat — e para a tela dizer o
// que está acontecendo com o gate, que é o detalhe mais fácil de esconder sem
// querer.

export interface LicenseOverview {
  seats_total: number
  seats_used: number
  seats_free: number
  tenants_total: number
  contracts_active: number
  enforcement_enabled: boolean
}

export interface AgentLicense {
  agent_login: string
  active: boolean
  modules: string[]
  assigned_at: string
  assigned_by: string | null
  revoked_at: string | null
}

export interface ModuleOption { value: string, label: string }

/** Percentual de uso, limitado a 100 (o teto pode ser reduzido depois). */
export function seatUsagePercent(o: Pick<LicenseOverview, 'seats_total' | 'seats_used'>): number {
  if (o.seats_total <= 0) return 0
  return Math.min(100, Math.round((o.seats_used / o.seats_total) * 100))
}

export type SeatTone = 'neutral' | 'warning' | 'error'

/**
 * A cor do quadro. Lotado é `error` e não `warning`: com o teto batido, a
 * próxima contratação de agente **falha**, e o operador precisa saber disso
 * antes de prometer acesso a alguém.
 */
export function seatTone(o: Pick<LicenseOverview, 'seats_total' | 'seats_used'>): SeatTone {
  if (o.seats_total <= 0) return 'neutral'
  if (o.seats_used >= o.seats_total) return 'error'
  if (o.seats_used / o.seats_total >= 0.8) return 'warning'
  return 'neutral'
}

/**
 * O aviso que a tela mostra quando o gate está desligado.
 *
 * Sem isto, o quadro mostraria módulos por agente e daria a entender que eles
 * controlam alguma coisa — quando, com a chave desligada, todo agente entra em
 * tudo. Um quadro que promete controle sem controlar é pior do que nenhum.
 */
export function enforcementNotice(o: LicenseOverview): string | null {
  if (o.enforcement_enabled) return null
  return 'Os módulos ainda NÃO restringem o acesso: a chave '
    + 'LICENSE_ENFORCEMENT_ENABLED está desligada. Atribua as licenças, confira '
    + 'este quadro e só então ligue — ligar antes tira o inventário de todos os agentes.'
}

/** Erros em português. Lista vazia = pode enviar. */
export function validateAssignment(
  login: string,
  modules: string[],
  overview: LicenseOverview,
  existing: AgentLicense | null,
): string[] {
  const errors: string[] = []
  if (!login.trim()) errors.push('Informe o login do agente.')
  // Reativar consome seat como atribuição nova — senão o teto seria burlável
  // revogando e reativando. Editar módulos de quem já tem licença, não.
  const consumesSeat = !existing || !existing.active
  if (consumesSeat && overview.seats_free <= 0) {
    errors.push(
      `Não há licença disponível: ${overview.seats_used} de ${overview.seats_total} em uso. `
      + 'Revogue uma licença ou aumente o total contratado.',
    )
  }
  return errors
}

/** Recusa reduzir o total abaixo do que já está em uso — espelha o sidecar. */
export function validateSeats(seats: number, overview: LicenseOverview): string[] {
  if (!Number.isInteger(seats) || seats < 0) return ['Informe um número inteiro maior ou igual a zero.']
  if (seats < overview.seats_used) {
    return [
      `Há ${overview.seats_used} licenças em uso — revogue antes de reduzir o total para ${seats}.`,
    ]
  }
  return []
}

export function moduleLabel(value: string, options: ModuleOption[]): string {
  return options.find(o => o.value === value)?.label ?? value
}

// ---- Teste V01, F5 — licença só para agente que existe no Znuny ----------
//
// O campo era livre (com placeholder "georgia", que parecia valor preenchido)
// e 6 das 7 licenças em uso eram de logins que não existem no Znuny. Agora o
// operador escolhe numa lista dos agentes reais e válidos; o sidecar continua
// sendo a verdade (422 "agente não existe").

export interface AgentSelectOption {
  value: string
  label: string
}

function str(v: unknown): string {
  return typeof v === 'string' ? v.trim() : ''
}

/**
 * Normaliza `GET /v1/admin/znuny/agents`. O sidecar devolve uma lista de
 * `{ login, first_name, last_name, valid }`; aceitamos também o envelope
 * `{ items: [...] }` com as chaves do Znuny (`UserLogin`, `ValidID`), que é o
 * formato que a tela de agentes espera — assim um ajuste do lado do sidecar
 * não esvazia o seletor. Só agentes VÁLIDOS: licenciar agente inativo é a
 * mesma armadilha do login inventado.
 */
export function normalizeZnunyAgents(raw: unknown): { login: string, name: string }[] {
  const list = Array.isArray(raw)
    ? raw
    : (raw && typeof raw === 'object' && Array.isArray((raw as { items?: unknown }).items))
        ? (raw as { items: unknown[] }).items
        : []
  const out: { login: string, name: string }[] = []
  const seen = new Set<string>()
  for (const item of list) {
    if (!item || typeof item !== 'object') continue
    const a = item as Record<string, unknown>
    const login = str(a.login) || str(a.UserLogin)
    if (!login || seen.has(login)) continue
    const valid = 'valid' in a ? a.valid === true : String(a.ValidID ?? '1') === '1'
    if (!valid) continue
    const name = [str(a.first_name) || str(a.UserFirstname), str(a.last_name) || str(a.UserLastname)]
      .filter(Boolean)
      .join(' ')
    seen.add(login)
    out.push({ login, name })
  }
  return out
}

/** "Nome (login)"; sem nome cadastrado, só o login. */
export function agentDisplayName(agent: { login: string, name: string }): string {
  return agent.name ? `${agent.name} (${agent.login})` : agent.login
}

/**
 * Opções do seletor. Quem já tem licença ATIVA continua na lista (é como se
 * edita os módulos dele), mas marcado. Uma licença de login que não existe no
 * Znuny só aparece se for a que está sendo editada agora — para o "Editar" da
 * tabela não deixar o seletor em branco —, marcada como tal.
 */
export function agentSelectOptions(
  agents: { login: string, name: string }[],
  licenses: AgentLicense[] | null | undefined,
  currentLogin = '',
): AgentSelectOption[] {
  const licensed = new Set((licenses ?? []).filter(l => l.active).map(l => l.agent_login))
  const options = [...agents]
    .sort((a, b) => agentDisplayName(a).localeCompare(agentDisplayName(b), 'pt-BR'))
    .map(a => ({
      value: a.login,
      label: licensed.has(a.login) ? `${agentDisplayName(a)} · já licenciado` : agentDisplayName(a),
    }))
  const current = currentLogin.trim()
  if (current && !agents.some(a => a.login === current)) {
    options.unshift({ value: current, label: `${current} · não existe no Znuny` })
  }
  return options
}

/**
 * Mensagem de erro do sidecar como ela veio. O 422 da licença traz `detail`
 * string ("7 de 9 em uso", "agente não existe", módulos válidos) — é o
 * próximo passo do operador. Validação do FastAPI (lista) vira as mensagens
 * juntas; qualquer outra coisa, a mensagem genérica.
 */
export function sidecarErrorMessage(err: unknown, fallback = 'Falha na operação.'): string {
  const detail = (err as { data?: { detail?: unknown } } | null)?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const msgs = detail
      .map(d => (d && typeof d === 'object' ? str((d as { msg?: unknown }).msg) : str(d)))
      .filter(Boolean)
    if (msgs.length) return msgs.join(' ')
  }
  return fallback
}
