// Saúde do sistema (Spec #3, V6) — formatação PURA das sondas devolvidas por
// GET /v1/admin/system/health. Cada sonda falha isolada (o HTTP continua 200;
// o campo vira {ok:false, message}); "asaas" pode nem trazer "ok" quando
// enabled=false. Ver contrato em
// docs/superpowers/plans/2026-07-30-spec-3-paridade-grounddesk.md, V6.
//
// Sonda "worker": avaliada pelo HEARTBEAT (last_tick_at = prova de vida a
// cada tick), não pelo cursor de sincronização (last_sync_at = última
// reconciliação de fato, só avança quando há trabalho). Cursor velho com
// heartbeat fresco é OCIOSO, não travado — a `message` já vem em português
// dizendo isso; a tela não pode reinterpretar isso como "atraso".

export interface ProbeResult {
  ok?: boolean
  enabled?: boolean
  latency_ms?: number
  message?: string
  last_tick_at?: string
  last_sync_at?: string
  ticks?: number
  last_error?: string
}

export interface SystemHealth {
  db: ProbeResult
  znuny_gi: ProbeResult
  worker: ProbeResult
  ai: ProbeResult
  asaas: ProbeResult
  version: string
}

export type HealthProbeKey = 'db' | 'znuny_gi' | 'worker' | 'ai' | 'asaas'

export interface HealthCardSpec {
  key: HealthProbeKey
  label: string
  icon: string
}

export const HEALTH_CARDS: HealthCardSpec[] = [
  { key: 'db', label: 'Banco de dados', icon: 'i-lucide-database' },
  { key: 'znuny_gi', label: 'Znuny (GI)', icon: 'i-lucide-server' },
  { key: 'worker', label: 'Worker de consumo', icon: 'i-lucide-cpu' },
  { key: 'ai', label: 'IA', icon: 'i-lucide-sparkles' },
  { key: 'asaas', label: 'Asaas', icon: 'i-lucide-credit-card' },
]

export type ProbeStatus = 'ok' | 'error' | 'disabled' | 'unknown'

// enabled:false é neutro (recurso desligado por opção), não é falha.
export function probeStatus(probe: ProbeResult | null | undefined): ProbeStatus {
  if (!probe) return 'unknown'
  if (probe.enabled === false) return 'disabled'
  if (probe.ok === true) return 'ok'
  if (probe.ok === false) return 'error'
  return 'unknown'
}

export function probeStatusColor(status: ProbeStatus): 'success' | 'error' | 'neutral' | 'warning' {
  switch (status) {
    case 'ok': return 'success'
    case 'error': return 'error'
    case 'disabled': return 'neutral'
    default: return 'warning'
  }
}

export function probeStatusLabel(status: ProbeStatus): string {
  switch (status) {
    case 'ok': return 'Operacional'
    case 'error': return 'Com falha'
    case 'disabled': return 'Desativado'
    default: return 'Desconhecido'
  }
}

export function formatLatency(ms: number | null | undefined): string | null {
  if (ms == null || !Number.isFinite(ms)) return null
  return `${ms} ms`
}

// Formata um timestamp ISO da sonda (last_tick_at/last_sync_at) em pt-BR.
// Não confundir com "atraso": quem decide se é ocioso ou travado é o `ok`
// da sonda + a `message` que o backend já manda pronta.
export function formatDateTime(iso: string | null | undefined): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleString('pt-BR')
}
