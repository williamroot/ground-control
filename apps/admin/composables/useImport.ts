// Importação em lote por CSV (T-R8.4, R8). Lógica PURA.
//
// O fluxo obrigatório é: baixar modelo → subir → **pré-visualizar** →
// confirmar. A pré-visualização não é conforto: importar 60 clientes e
// descobrir no 47º que a planilha tinha uma coluna trocada é o erro que ela
// existe para evitar.

export type ImportKind = 'tenants' | 'tenant_users'

export interface ImportRow {
  line: number
  status: 'ok' | 'created' | 'skipped' | 'failed'
  key: string
  message: string
  generated_password: string | null
}

export interface ImportReport {
  kind: string
  dry_run: boolean
  total: number
  valid: number
  invalid: number
  created: number
  skipped: number
  failed: number
  rows: ImportRow[]
}

export const IMPORT_KINDS = [
  { label: 'Clientes', value: 'tenants' },
  { label: 'Usuários de um cliente', value: 'tenant_users' },
]

export const STATUS_LABELS: Record<string, string> = {
  ok: 'Pronta para importar',
  created: 'Criada',
  skipped: 'Já existia',
  failed: 'Recusada',
}

export const STATUS_COLORS: Record<string, string> = {
  ok: 'primary',
  created: 'success',
  skipped: 'neutral',
  failed: 'error',
}

/**
 * Só se importa depois de simular, e só se houver linha aproveitável.
 * Um arquivo 100% inválido não deve nem oferecer o botão.
 */
export function canRun(report: ImportReport | null): boolean {
  return !!report && report.dry_run && report.valid > 0
}

/** "Criar 47 clientes?" — a confirmação diz o NÚMERO, não "confirma?". */
export function confirmationLabel(report: ImportReport | null, kind: ImportKind): string {
  if (!report) return ''
  const what = kind === 'tenants' ? 'cliente' : 'usuário'
  const n = report.valid
  return `Importar ${n} ${what}${n === 1 ? '' : 's'}?`
}

/**
 * Conteúdo de célula vindo de planilha é entrada NÃO-CONFIÁVEL. Uma célula
 * começando com `=`, `+`, `-` ou `@` é interpretada como fórmula por Excel e
 * Sheets — o clássico CSV injection. A tela nunca renderiza HTML disso, e
 * aqui neutralizamos o gatilho de fórmula ao exibir.
 */
export function safeCell(value: string): string {
  const v = String(value ?? '')
  return /^[=+\-@\t\r]/.test(v) ? `'${v}` : v
}

/** Resumo humano do resultado, para o toast e para o topo da tabela. */
export function summarize(report: ImportReport): string {
  if (report.dry_run) {
    return `${report.valid} pronta(s), ${report.invalid} com problema, de ${report.total} linha(s).`
  }
  return `${report.created} criada(s), ${report.skipped} já existia(m), ${report.failed} falhou(aram).`
}
