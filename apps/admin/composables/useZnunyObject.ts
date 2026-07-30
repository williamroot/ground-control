// Spec #4 — lógica pura das telas que administram o Znuny ao vivo via GI
// (`/znuny/filas`, `/znuny/sla`). Sem Nuxt/DOM: normalização da resposta do
// sidecar, rascunho/validação/montagem de payload para Fila e SLA, e o
// formatador de minutos→legível. O sidecar (Znuny) é a fonte de verdade — a
// validação aqui é só espelho leve para feedback imediato (o 422 do Znuny
// prevalece e é exibido como veio).
//
// Nota de contrato: o backend (sidecar + Perl) está sendo escrito em paralelo
// contra o mesmo documento de spec, que descreve os campos mas não fixa a
// forma exata do JSON de `AdminObjectList`. `extractItems`/`extractSupport`
// abaixo são deliberadamente tolerantes a variações razoáveis de formato
// (lista solta vs. envelope `{ items, support }`, dicionário id→nome vs.
// lista `[{id,name}]`) para não quebrar por causa de um wrapper diferente.

export interface ZnunyOption {
  id: string
  name: string
}

// Normaliza uma lista de apoio (GroupList/ValidList/CalendarList/
// StateTypeList) — aceita dicionário {id: nome} ou lista [{id, name}].
export function toOptions(input: unknown): ZnunyOption[] {
  if (!input) return []
  if (Array.isArray(input)) {
    return input.map((entry) => {
      if (entry && typeof entry === 'object') {
        const e = entry as Record<string, unknown>
        const id = e.id ?? e.ID ?? e.Key
        const name = e.name ?? e.Name ?? e.Value ?? id
        return { id: String(id), name: String(name) }
      }
      return { id: String(entry), name: String(entry) }
    })
  }
  if (typeof input === 'object') {
    return Object.entries(input as Record<string, unknown>).map(([id, name]) => ({
      id,
      name: String(name),
    }))
  }
  return []
}

// Extrai a lista de itens da resposta de AdminObjectList, tolerando um
// envelope `{ items: [...] }`, `{ <Objeto>: [...] }` ou a lista solta.
export function extractItems(data: unknown, objectKey: string): Record<string, unknown>[] {
  if (Array.isArray(data)) return data as Record<string, unknown>[]
  if (data && typeof data === 'object') {
    const d = data as Record<string, unknown>
    const candidate = d.items ?? d[objectKey] ?? d[`${objectKey}List`] ?? d.list
    if (Array.isArray(candidate)) return candidate as Record<string, unknown>[]
  }
  return []
}

// Extrai as listas de apoio da resposta de AdminObjectList, tolerando um
// envelope `{ support: {...} }` ou as chaves soltas ao lado dos itens.
export function extractSupport(data: unknown): Record<string, unknown> {
  if (data && typeof data === 'object') {
    const d = data as Record<string, unknown>
    if (d.support && typeof d.support === 'object') return d.support as Record<string, unknown>
    return d
  }
  return {}
}

// Chave numérica/id de um item retornado pelo Znuny — o nome do campo PK
// varia por objeto (QueueID, SLAID, ServiceID...); tentamos os candidatos
// conhecidos antes de cair em ID/id genérico.
export function extractItemId(item: Record<string, unknown>): string {
  const candidates = ['QueueID', 'SLAID', 'ServiceID', 'TypeID', 'StateID', 'PriorityID', 'ID', 'id']
  for (const key of candidates) {
    const v = item[key]
    if (v !== undefined && v !== null && v !== '') return String(v)
  }
  return ''
}

// Minutos → texto legível ("240 min · 4 h"). 0 é o valor que o Znuny usa para
// "sem tempo definido" nesses campos — sinalizamos isso em vez de "0 h".
export function formatMinutes(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const n = typeof value === 'string' ? Number(value) : value
  if (!Number.isFinite(n)) return '—'
  if (n === 0) return 'desativado (0 min)'
  const hours = n / 60
  const hoursText = Number.isInteger(hours) ? String(hours) : hours.toFixed(1)
  return `${n} min · ${hoursText} h`
}

// Nomes do ValidList vêm do Znuny em inglês (`valid`/`invalid`/
// `invalid-temporarily`) — traduzido pra pt-BR na UI; nome desconhecido cai
// no valor original em vez de sumir.
const VALID_LABEL_PT: Record<string, string> = {
  'valid': 'Válido',
  'invalid': 'Inválido',
  'invalid-temporarily': 'Inválido temporariamente',
}

export function validLabelPt(name: string): string {
  return VALID_LABEL_PT[name.toLowerCase()] ?? name
}

export function validBadgeColor(id: string): 'success' | 'warning' | 'error' | 'neutral' {
  if (id === '1') return 'success'
  if (id === '2') return 'error'
  if (id === '3') return 'warning'
  return 'neutral'
}

function minutesFieldError(value: string, label: string): string | null {
  if (value.trim() === '') return null
  const n = Number(value)
  if (!Number.isInteger(n) || n < 0) {
    return `${label} deve ser um número inteiro de minutos (≥ 0).`
  }
  return null
}

function percentFieldError(value: string, label: string): string | null {
  if (value.trim() === '') return null
  const n = Number(value)
  if (!Number.isInteger(n) || n < 0 || n > 100) {
    return `${label} deve ser um número inteiro entre 0 e 100.`
  }
  return null
}

// --- Fila (Queue) ------------------------------------------------------------

export interface QueueDraft {
  Name: string
  GroupID: string
  Comment: string
  ValidID: string
  FirstResponseTime: string
  UpdateTime: string
  SolutionTime: string
  Calendar: string
  FollowUpID: string
  UnlockTimeout: string
}

export function emptyQueueDraft(): QueueDraft {
  return {
    Name: '',
    GroupID: '',
    Comment: '',
    ValidID: '1',
    FirstResponseTime: '',
    UpdateTime: '',
    SolutionTime: '',
    Calendar: '',
    FollowUpID: '',
    UnlockTimeout: '',
  }
}

export function queueDraftFromItem(item: Record<string, unknown>): QueueDraft {
  const str = (v: unknown, fallback = '') => (v === null || v === undefined ? fallback : String(v))
  return {
    Name: str(item.Name),
    GroupID: str(item.GroupID),
    Comment: str(item.Comment),
    ValidID: str(item.ValidID, '1'),
    FirstResponseTime: str(item.FirstResponseTime),
    UpdateTime: str(item.UpdateTime),
    SolutionTime: str(item.SolutionTime),
    Calendar: str(item.Calendar),
    FollowUpID: str(item.FollowUpID),
    UnlockTimeout: str(item.UnlockTimeout),
  }
}

export function validateQueueDraft(draft: QueueDraft): string[] {
  const errors: string[] = []
  const name = draft.Name.trim()
  if (name.length < 2 || name.length > 200) errors.push('Nome deve ter entre 2 e 200 caracteres.')
  if (!draft.GroupID.trim()) errors.push('Selecione um grupo.')
  if (!draft.ValidID.trim()) errors.push('Selecione a validade.')
  const minuteChecks: [string, string][] = [
    [draft.FirstResponseTime, 'Tempo de 1ª resposta'],
    [draft.UpdateTime, 'Tempo de atualização'],
    [draft.SolutionTime, 'Tempo de solução'],
    [draft.UnlockTimeout, 'Tempo de desbloqueio automático'],
  ]
  for (const [value, label] of minuteChecks) {
    const err = minutesFieldError(value, label)
    if (err) errors.push(err)
  }
  if (draft.FollowUpID.trim() !== '' && !/^\d+$/.test(draft.FollowUpID.trim())) {
    errors.push('Follow-up deve ser um id numérico.')
  }
  return errors
}

export function isQueueDraftValid(draft: QueueDraft): boolean {
  return validateQueueDraft(draft).length === 0
}

export interface QueuePayload {
  Name: string
  GroupID: number
  Comment?: string
  ValidID: number
  FirstResponseTime?: number
  UpdateTime?: number
  SolutionTime?: number
  Calendar?: string
  FollowUpID?: number
  UnlockTimeout?: number
}

export function buildQueuePayload(draft: QueueDraft): QueuePayload {
  const int = (v: string) => (v.trim() === '' ? undefined : Number(v))
  return {
    Name: draft.Name.trim(),
    GroupID: Number(draft.GroupID),
    Comment: draft.Comment.trim() || undefined,
    ValidID: Number(draft.ValidID),
    FirstResponseTime: int(draft.FirstResponseTime),
    UpdateTime: int(draft.UpdateTime),
    SolutionTime: int(draft.SolutionTime),
    Calendar: draft.Calendar.trim() || undefined,
    FollowUpID: int(draft.FollowUpID),
    UnlockTimeout: int(draft.UnlockTimeout),
  }
}

// Payload de invalidação (ValidID=2) — no Znuny não existe exclusão de fila,
// só isso. Mantém os demais campos do rascunho intactos.
export function buildInvalidateQueuePayload(draft: QueueDraft): QueuePayload {
  return buildQueuePayload({ ...draft, ValidID: '2' })
}

// --- SLA -----------------------------------------------------------------

export interface SlaDraft {
  Name: string
  Comment: string
  ValidID: string
  Calendar: string
  FirstResponseTime: string
  FirstResponseNotify: string
  UpdateTime: string
  UpdateNotify: string
  SolutionTime: string
  SolutionNotify: string
  ServiceIDs: string[]
}

export function emptySlaDraft(): SlaDraft {
  return {
    Name: '',
    Comment: '',
    ValidID: '1',
    Calendar: '',
    FirstResponseTime: '',
    FirstResponseNotify: '',
    UpdateTime: '',
    UpdateNotify: '',
    SolutionTime: '',
    SolutionNotify: '',
    ServiceIDs: [],
  }
}

export function slaDraftFromItem(item: Record<string, unknown>): SlaDraft {
  const str = (v: unknown, fallback = '') => (v === null || v === undefined ? fallback : String(v))
  const rawServiceIds = item.ServiceIDs
  const serviceIds = Array.isArray(rawServiceIds) ? rawServiceIds.map(v => String(v)) : []
  return {
    Name: str(item.Name),
    Comment: str(item.Comment),
    ValidID: str(item.ValidID, '1'),
    Calendar: str(item.Calendar),
    FirstResponseTime: str(item.FirstResponseTime),
    FirstResponseNotify: str(item.FirstResponseNotify),
    UpdateTime: str(item.UpdateTime),
    UpdateNotify: str(item.UpdateNotify),
    SolutionTime: str(item.SolutionTime),
    SolutionNotify: str(item.SolutionNotify),
    ServiceIDs: serviceIds,
  }
}

export function validateSlaDraft(draft: SlaDraft): string[] {
  const errors: string[] = []
  const name = draft.Name.trim()
  if (name.length < 2 || name.length > 200) errors.push('Nome deve ter entre 2 e 200 caracteres.')
  if (!draft.ValidID.trim()) errors.push('Selecione a validade.')
  const minuteChecks: [string, string][] = [
    [draft.FirstResponseTime, 'Tempo de 1ª resposta'],
    [draft.UpdateTime, 'Tempo de atualização'],
    [draft.SolutionTime, 'Tempo de solução'],
  ]
  for (const [value, label] of minuteChecks) {
    const err = minutesFieldError(value, label)
    if (err) errors.push(err)
  }
  const percentChecks: [string, string][] = [
    [draft.FirstResponseNotify, 'Notificação de 1ª resposta'],
    [draft.UpdateNotify, 'Notificação de atualização'],
    [draft.SolutionNotify, 'Notificação de solução'],
  ]
  for (const [value, label] of percentChecks) {
    const err = percentFieldError(value, label)
    if (err) errors.push(err)
  }
  return errors
}

export function isSlaDraftValid(draft: SlaDraft): boolean {
  return validateSlaDraft(draft).length === 0
}

export interface SlaPayload {
  Name: string
  Comment?: string
  ValidID: number
  Calendar?: string
  FirstResponseTime?: number
  FirstResponseNotify?: number
  UpdateTime?: number
  UpdateNotify?: number
  SolutionTime?: number
  SolutionNotify?: number
  ServiceIDs: number[]
}

export function buildSlaPayload(draft: SlaDraft): SlaPayload {
  const int = (v: string) => (v.trim() === '' ? undefined : Number(v))
  return {
    Name: draft.Name.trim(),
    Comment: draft.Comment.trim() || undefined,
    ValidID: Number(draft.ValidID),
    Calendar: draft.Calendar.trim() || undefined,
    FirstResponseTime: int(draft.FirstResponseTime),
    FirstResponseNotify: int(draft.FirstResponseNotify),
    UpdateTime: int(draft.UpdateTime),
    UpdateNotify: int(draft.UpdateNotify),
    SolutionTime: int(draft.SolutionTime),
    SolutionNotify: int(draft.SolutionNotify),
    ServiceIDs: draft.ServiceIDs.map(Number),
  }
}

export function buildInvalidateSlaPayload(draft: SlaDraft): SlaPayload {
  return buildSlaPayload({ ...draft, ValidID: '2' })
}
