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
