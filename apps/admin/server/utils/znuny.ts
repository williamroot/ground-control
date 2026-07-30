// Spec #4 — allowlist compartilhada pelos proxies genéricos de administração
// do Znuny (`/api/admin/znuny/objects/[object]/**`). Espelha a allowlist do
// dispatcher Perl (`AdminSpec.pm`) por defesa em profundidade — a chave nunca
// vira classe/método Perl aqui, é só o portão de entrada do console. Objeto
// fora da tabela → 400 sem tentar chamar o sidecar.
export const ZNUNY_OBJECT_KEYS = ['Queue', 'SLA', 'Service', 'Type', 'State', 'Priority'] as const
export type ZnunyObjectKey = typeof ZNUNY_OBJECT_KEYS[number]

export function isZnunyObjectKey(value: string | null | undefined): value is ZnunyObjectKey {
  return !!value && (ZNUNY_OBJECT_KEYS as readonly string[]).includes(value)
}

// Mesmo guard usado nos outros proxies com path param numérico (faturas,
// tokens) — id malformado é 400, não repassa pro sidecar.
export function isNumericId(value: string | null | undefined): boolean {
  return !!value && /^[0-9]+$/.test(value)
}
