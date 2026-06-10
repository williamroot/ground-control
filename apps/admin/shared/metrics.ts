// Transforms the /dashboard/metrics (and /admin/analytics) payload into the
// inputs the SVG charts expect. Pure functions (no Nuxt/DOM) — unit-testable and
// shared by portal + console. H8: ticket-state donut uses SEMANTIC tones (SLA/
// estados), never the brand var; the by-day area + CSAT bars carry the brand.

export type Tone = 'error' | 'warning' | 'success' | 'info' | 'neutral'

export interface TicketStatsBlock {
  by_state: Record<string, number>
  by_priority: Record<string, number>
  by_day: { date: string, count: number }[]
  sla_breached: number
  sla_at_risk: number
  total: number
}

export interface CsatBlock {
  avg: number | null
  count: number
  distribution: Record<string, number>
}

export interface BalanceBlock {
  contract_count: number
  contracts: {
    contract_id: string
    code: string
    type: string
    kind: string
    remaining: number | null
    consumed_percent: number | null
  }[]
  low_balance_alerts: unknown[]
}

export interface DashboardMetrics {
  period_days: number
  tickets: TicketStatsBlock | null
  csat: CsatBlock
  hours: { total_minutes: number, total_hours: number }
  balance: BalanceBlock
}

// State name -> semantic tone for the by-state donut (H8). Maps the common
// Znuny state families; unknowns fall back to neutral.
export function stateTone(state: string): Tone {
  const s = state.toLowerCase()
  if (s.includes('closed') || s.includes('resolved') || s.includes('successful')) return 'success'
  if (s.includes('pending') || s.includes('reminder') || s.includes('wait')) return 'warning'
  if (s.includes('removed') || s.includes('merged') || s.includes('rejected')) return 'neutral'
  if (s.includes('open') || s.includes('new')) return 'info'
  return 'neutral'
}

// Donut segments for tickets by state (semantic palette).
export function ticketStateSegments(
  tickets: TicketStatsBlock | null,
): { label: string, value: number, tone: Tone }[] {
  if (!tickets) return []
  return Object.entries(tickets.by_state)
    .filter(([, v]) => v > 0)
    .map(([label, value]) => ({ label, value, tone: stateTone(label) }))
}

// Area-chart points for ticket volume per day (brand identity).
export function ticketVolumePoints(
  tickets: TicketStatsBlock | null,
): { bucket: string, value: number }[] {
  if (!tickets) return []
  return tickets.by_day.map(d => ({ bucket: d.date, value: d.count }))
}

// Bar-chart bars for the CSAT 1..5 distribution (brand identity).
export function csatBars(csat: CsatBlock): { label: string, value: number }[] {
  return [1, 2, 3, 4, 5].map(score => ({
    label: String(score),
    value: Number(csat.distribution?.[String(score)] ?? 0),
  }))
}
