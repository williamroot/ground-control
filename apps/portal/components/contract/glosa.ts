export type GlosaStatus = 'pending' | 'approved' | 'rejected'
export interface GlosaMeta { label: string, classes: string, strike: boolean }
// Fixed semantic colors — never brand (H8).
export function glosaMeta(status: GlosaStatus | null): GlosaMeta | null {
  if (status === null) return null
  if (status === 'approved') return { label: 'Glosado (não conta)', classes: 'text-error', strike: true }
  if (status === 'pending') return { label: 'Glosa em análise', classes: 'text-warning', strike: false }
  return { label: 'Glosa rejeitada', classes: 'text-muted', strike: false }
}
