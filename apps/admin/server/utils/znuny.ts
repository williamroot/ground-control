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

// ── Onda 1 (R1/R2/R5) — guards dos proxies de cliente ──────────────────────
//
// Os proxies novos interpolam `id` de tenant e `login` de usuário direto na
// URL do sidecar. Sem guard, um `login` com `../` sobe um nível de path e vira
// uma chamada a outro endpoint do sidecar com o cookie de agente junto —
// exatamente o que não pode acontecer. Validar aqui é defesa em profundidade:
// o sidecar também recusa.

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** Id de tenant precisa ser UUID — qualquer outra coisa é 404, sem chamar o sidecar. */
export function isTenantId(value: string | null | undefined): boolean {
  return !!value && UUID_RE.test(value)
}

/**
 * Login de usuário de cliente é o e-mail. Recusa tudo que possa mexer no path
 * (`/`, `\`, `..`, `%`) ou quebrar a requisição (espaço, caractere de controle).
 */
export function isCustomerLogin(value: string | null | undefined): boolean {
  if (!value) return false
  if (value.length > 255) return false
  if (/[/\\%\s]/.test(value)) return false
  if (value.includes('..')) return false
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f\u007f]/.test(value)) return false
  return value.includes('@')
}
