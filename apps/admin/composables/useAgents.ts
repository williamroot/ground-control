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
