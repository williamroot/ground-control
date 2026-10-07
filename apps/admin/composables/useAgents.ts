// #1R-a — lógica pura do console de Agentes de inventário. Mantida fora dos
// componentes para testar sem montar o Nuxt (lição #1M..#1Q). Cores semânticas
// (H8): active=success, pending=warning, offline=neutral, revoked=error — nunca
// a cor de marca (reservada à navegação/identidade).

export type DeviceStatus = 'active' | 'pending' | 'revoked'
export type EffectiveStatus = DeviceStatus | 'offline'

export interface Device {
  id: string
  hostname: string
  status: DeviceStatus
  os: string | null
  fingerprint: string
  znuny_config_item_id: number | null
  specs: Record<string, unknown>
  last_seen_at: string | null
  enrolled_at: string | null
}

export interface AgentToken {
  id: string
  label: string
  max_registrations: number | null
  registration_count: number
  enabled: boolean
  expires_at: string | null
  created_at: string
}

/** Monta o comando de instalação parametrizado (mostrado uma vez por token). */
export function buildInstallCommand(server: string, token: string): string {
  const base = server.replace(/\/+$/, '')
  return `curl -fsSL ${base}/install.sh | sh -s -- --enroll-token=${token} --server=${base}`
}

/**
 * Offline = device active cujo último contato passou de 2× o intervalo de
 * heartbeat (ou nunca contatou). Só faz sentido para devices que deveriam estar
 * batendo heartbeat; pending/revoked são tratados em effectiveStatus.
 */
export function isOffline(lastSeenAt: string | null, intervalSeconds: number): boolean {
  if (!lastSeenAt) return true
  const last = new Date(lastSeenAt).getTime()
  if (Number.isNaN(last)) return true
  const ageSeconds = (Date.now() - last) / 1000
  return ageSeconds > 2 * intervalSeconds
}

/** Status efetivo exibido: active vira offline se sem contato; pending/revoked intactos. */
export function effectiveStatus(
  status: DeviceStatus,
  lastSeenAt: string | null,
  intervalSeconds: number,
): EffectiveStatus {
  if (status === 'active' && isOffline(lastSeenAt, intervalSeconds)) return 'offline'
  return status
}

const STATUS_COLOR: Record<EffectiveStatus, 'success' | 'warning' | 'neutral' | 'error'> = {
  active: 'success',
  pending: 'warning',
  offline: 'neutral',
  revoked: 'error',
}

export function deviceStatusColor(status: EffectiveStatus): 'success' | 'warning' | 'neutral' | 'error' {
  return STATUS_COLOR[status] ?? 'neutral'
}

const STATUS_LABEL: Record<EffectiveStatus, string> = {
  active: 'Ativo',
  pending: 'Pendente',
  offline: 'Offline',
  revoked: 'Revogado',
}

export function deviceStatusLabel(status: EffectiveStatus): string {
  return STATUS_LABEL[status] ?? status
}

/** Resumo curto das specs para a tabela (cpu · memória · disco). */
export function specsSummary(specs: Record<string, unknown>): string {
  const parts = ['cpu', 'memory', 'disk']
    .map(k => specs[k])
    .filter((v): v is string => typeof v === 'string' && v.length > 0)
  return parts.join(' · ')
}

// ---- Bloqueio por licença (R16 com LICENSE_ENFORCEMENT_ENABLED=true) -------
//
// Sem o módulo `inventory` na licença do agente logado, o sidecar responde 403
// (`{"detail": "licença sem o módulo 'inventory'"}`) em devices e agent-tokens.
// A página engolia o erro e mostrava "Nenhum token ativo" / "Nenhum
// dispositivo": parecia VAZIA, não BLOQUEADA (caso da Georgia, teste V01).
// O resultado de cada carga é explícito — ok, bloqueado ou erro — e é
// serializável, então vale igual no SSR (carga direta pela URL).

export type LoadOutcome<T>
  = | { status: 'ok', data: T }
    | { status: 'blocked' }
    | { status: 'error' }

/** Status HTTP de um erro do `$fetch` (ofetch usa `statusCode`/`status`/`response.status`). */
export function httpStatusOf(err: unknown): number | null {
  const e = err as { statusCode?: unknown, status?: unknown, response?: { status?: unknown } } | null
  for (const v of [e?.statusCode, e?.status, e?.response?.status]) {
    if (typeof v === 'number') return v
  }
  return null
}

/** 403 = a licença do agente não inclui o módulo. Qualquer outra falha é erro comum. */
export function isModuleBlocked(err: unknown): boolean {
  return httpStatusOf(err) === 403
}

export function okOutcome<T>(data: T): LoadOutcome<T> {
  return { status: 'ok', data }
}

export function failureOutcome(err: unknown): LoadOutcome<never> {
  return isModuleBlocked(err) ? { status: 'blocked' } : { status: 'error' }
}

/** Basta UMA carga bloqueada para a página inteira virar o estado de bloqueio. */
export function anyBlocked(...outcomes: (LoadOutcome<unknown> | null | undefined)[]): boolean {
  return outcomes.some(o => o?.status === 'blocked')
}

/** Dados de uma carga ok; `null` quando bloqueada, com erro ou ainda sem resposta. */
export function outcomeData<T>(o: LoadOutcome<T> | null | undefined): T | null {
  return o?.status === 'ok' ? o.data : null
}

export const INVENTORY_BLOCKED_TITLE = 'Sua licença não inclui o módulo Inventário'
export const INVENTORY_BLOCKED_HINT = 'Peça a um administrador para incluir o módulo em Licenças.'
