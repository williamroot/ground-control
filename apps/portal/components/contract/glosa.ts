export type GlosaStatus = 'pending' | 'approved' | 'rejected'
export interface GlosaMeta { label: string, classes: string, strike: boolean }
// Fixed semantic colors — never brand (H8).
export function glosaMeta(status: GlosaStatus | null): GlosaMeta | null {
  if (status === null) return null
  if (status === 'approved') return { label: 'Glosado (não conta)', classes: 'text-red-700', strike: true }
  if (status === 'pending') return { label: 'Glosa em análise', classes: 'text-amber-700', strike: false }
  return { label: 'Glosa rejeitada', classes: 'text-neutral-500', strike: false }
}
