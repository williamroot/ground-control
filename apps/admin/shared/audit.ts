// Rótulos/cores da trilha de auditoria (Spec #3, V5) — em shared/ por causa da
// import-protection do Nuxt (importável por #shared, igual a contracts.ts).
// H8: cor SEMÂNTICA por tipo de ação, nunca a cor de marca.

export type AuditAction = 'create' | 'update' | 'delete' | 'login' | 'export'

export const AUDIT_ACTIONS: AuditAction[] = ['create', 'update', 'delete', 'login', 'export']

export type AuditBadgeColor = 'success' | 'info' | 'error' | 'neutral' | 'warning'

const ACTION_META: Record<AuditAction, { label: string, color: AuditBadgeColor }> = {
  create: { label: 'Criação', color: 'success' },
  update: { label: 'Atualização', color: 'info' },
  delete: { label: 'Exclusão', color: 'error' },
  login: { label: 'Login', color: 'neutral' },
  export: { label: 'Exportação', color: 'warning' },
}

export function actionLabel(action: string): string {
  return (ACTION_META as Record<string, { label: string }>)[action]?.label ?? action
}

export function actionColor(action: string): AuditBadgeColor {
  return (ACTION_META as Record<string, { color: AuditBadgeColor }>)[action]?.color ?? 'neutral'
}

const ACTOR_TYPE_LABEL: Record<string, string> = {
  agent: 'Agente',
  customer: 'Cliente',
  system: 'Sistema',
}

// Ator exibido na tabela: login quando houver, senão o tipo por extenso.
export function actorLabel(actorType: string | null | undefined, actorLogin: string | null | undefined): string {
  if (actorLogin && actorLogin.trim()) return actorLogin
  return ACTOR_TYPE_LABEL[actorType ?? ''] ?? (actorType || 'Desconhecido')
}

// Entidade exibida como "entity · entity_id" (ou só "entity" sem id).
export function entityLabel(entity: string, entityId: string | null | undefined): string {
  return entityId ? `${entity} · ${entityId}` : entity
}

export const MAX_AUDIT_LIMIT = 200
export const DEFAULT_AUDIT_LIMIT = 50

// Trava client-side espelhando o 422 do sidecar (limit máximo 200).
export function clampAuditLimit(limit: number): number {
  if (!Number.isFinite(limit) || limit <= 0) return DEFAULT_AUDIT_LIMIT
  return Math.min(Math.trunc(limit), MAX_AUDIT_LIMIT)
}
