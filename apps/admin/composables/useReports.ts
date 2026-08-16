// Relatórios do console (Onda 3, R18a/R18b). Lógica PURA, testável sem Nuxt.
//
// Duas telas comem daqui:
//  • consumo por cliente (R18a) — o gráfico dos "últimos três meses"
//  • relatório executivo mensal (R18b) — mês + cliente → PDF
//
// A regra que mais importa está em `unitLabel`/`groupSeriesByKind`: contrato de
// hora mostra **h**, contrato de crédito mostra **R$**, e os dois NUNCA no
// mesmo gráfico. Isso é requisito do vídeo (11:00), não detalhe estético —
// somar horas com reais não é arredondamento, é número errado.

export type SeriesKind = 'hours' | 'brl' | 'services' | 'n/a'
export type WindowMode = 'cycles' | 'months'

export interface SeriesPoint {
  bucket: string
  value: number
}

export interface ContractSeries {
  contract_id: string
  code: string
  type: string
  kind: SeriesKind
  points: SeriesPoint[]
}

export interface ConsumptionSeriesResponse {
  tenant_id: string
  window: WindowMode
  count: number
  series: ContractSeries[]
}

export interface ReportTopItem { label: string, count: number }

export interface ReportConsumption {
  code: string
  type: string
  kind: SeriesKind
  value: number
  unit_label: string
}

export interface ReportTicket {
  znuny_ticket_id: number
  ticket_number: string
  title: string
  state: string
  service: string
  type: string
  created: string
  hours: number
}

export interface MonthlyReport {
  tenant_id: string
  tenant_name: string
  display_name: string
  month: string
  month_label: string
  period_start: string
  period_end: string
  consumption: ReportConsumption[]
  dimension: string
  dimension_label: string
  top_items: ReportTopItem[]
  tickets: ReportTicket[]
  ticket_total: number
  tickets_truncated: boolean
  degraded: boolean
}

/** Sufixo da unidade no eixo. `n/a` não tem eixo — não tem gráfico. */
export function unitLabel(kind: SeriesKind | string): string {
  switch (kind) {
    case 'hours': return 'h'
    case 'brl': return 'R$'
    case 'services': return 'atend.'
    default: return ''
  }
}

/** Valor já formatado na unidade certa, pt-BR. */
export function formatValue(kind: SeriesKind | string, value: number): string {
  if (kind === 'brl') {
    return value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
  }
  if (kind === 'hours') return `${value.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} h`
  if (kind === 'services') return `${Math.round(value)} atend.`
  return '—'
}

/**
 * Agrupa as séries por unidade. Um cliente com banco de horas e crédito em
 * reais rende DOIS grupos, e a tela desenha um gráfico por grupo.
 * Séries `n/a` (valor fechado, SaaS) somem: gráfico vazio engana (A18a.4).
 */
export function groupSeriesByKind(series: ContractSeries[]): { kind: SeriesKind, series: ContractSeries[] }[] {
  const groups = new Map<SeriesKind, ContractSeries[]>()
  for (const s of series) {
    if (s.kind === 'n/a') continue
    const list = groups.get(s.kind) ?? []
    list.push(s)
    groups.set(s.kind, list)
  }
  return [...groups.entries()].map(([kind, list]) => ({ kind, series: list }))
}

/** Rótulo curto do balde: '2026-06-01' → 'jun/26'. */
const MONTHS_SHORT = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']

export function bucketLabel(bucket: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(bucket)
  if (!m) return bucket
  const month = Number(m[2])
  if (month < 1 || month > 12) return bucket
  return `${MONTHS_SHORT[month - 1]}/${m[1]!.slice(2)}`
}

/**
 * `'2026-05'` → `('2026-05-01', '2026-05-31')`; qualquer outra coisa → `null`.
 * A tela usa o `null` para NÃO chamar a API — o backend também recusa, mas o
 * operador não precisa de um round-trip para descobrir que digitou 2026-13.
 */
export function monthRange(month: string): [string, string] | null {
  if (!/^\d{4}-\d{2}$/.test(month)) return null
  const year = Number(month.slice(0, 4))
  const mon = Number(month.slice(5))
  if (mon < 1 || mon > 12) return null
  if (year < 2000 || year > 2100) return null
  const last = new Date(Date.UTC(year, mon, 0)).getUTCDate()
  return [`${month}-01`, `${month}-${String(last).padStart(2, '0')}`]
}

export function isValidMonth(month: string): boolean {
  return monthRange(month) !== null
}

/** 'YYYY-MM' do mês anterior ao de hoje — o padrão útil da tela. */
export function previousMonth(today: Date = new Date()): string {
  const d = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), 1))
  d.setUTCMonth(d.getUTCMonth() - 1)
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`
}

export function monthLabelPt(month: string): string {
  const full = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
    'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
  if (!isValidMonth(month)) return month
  return `${full[Number(month.slice(5)) - 1]}/${month.slice(0, 4)}`
}
