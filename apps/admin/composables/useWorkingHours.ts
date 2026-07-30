// Calendário do Znuny — jornada de trabalho e feriados (Spec #4, Bloco D).
// Lógica PURA (sem Nuxt/DOM), testável isoladamente. É a parte "de verdade"
// desta tela: converte entre a grade clicável da UI e o formato de SysConfig
// do Znuny (`TimeWorkingHours` = Dia -> lista de horas inteiras 0-23;
// `TimeVacationDays` = Mês -> Dia -> texto; `TimeVacationDaysOneTime` =
// Ano -> Mês -> Dia -> texto), valida a forma ANTES de mandar pro sidecar
// (espelho leve do 422 — a verdade é sempre o servidor) e calcula o total
// semanal que o operador confere antes de salvar.

export type DayKey = 'Mon' | 'Tue' | 'Wed' | 'Thu' | 'Fri' | 'Sat' | 'Sun'

export const DAY_KEYS: DayKey[] = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export const DAY_LABELS: Record<DayKey, string> = {
  Mon: 'Segunda',
  Tue: 'Terça',
  Wed: 'Quarta',
  Thu: 'Quinta',
  Fri: 'Sexta',
  Sat: 'Sábado',
  Sun: 'Domingo',
}

export const DAY_LABELS_SHORT: Record<DayKey, string> = {
  Mon: 'Seg',
  Tue: 'Ter',
  Wed: 'Qua',
  Thu: 'Qui',
  Fri: 'Sex',
  Sat: 'Sáb',
  Sun: 'Dom',
}

export const HOURS: number[] = Array.from({ length: 24 }, (_, h) => h)

// Grade da UI: cada dia -> 24 posições (índice = hora), true = hora útil.
export type WorkingGrid = Record<DayKey, boolean[]>

export function emptyGrid(): WorkingGrid {
  const grid = {} as WorkingGrid
  for (const day of DAY_KEYS) grid[day] = Array.from({ length: 24 }, () => false)
  return grid
}

// ---- Seletor de calendário (Calendar1..9 além do padrão) ------------------

// O calendário padrão do Znuny é o sufixo VAZIO (`TimeWorkingHours`, sem
// `::CalendarN`). Mas o `USelect` do Nuxt UI recusa item com valor string vazia
// — string vazia é o sinal de "sem seleção" dele — e derrubava a página inteira
// com erro 500 no SSR. Por isso a UI usa o sentinela `default` e a conversão
// para o sufixo real acontece só na borda da API (`calendarToQuery`).
export const DEFAULT_CALENDAR = 'default'

export const CALENDAR_OPTIONS: { value: string, label: string }[] = [
  { value: DEFAULT_CALENDAR, label: 'Padrão' },
  ...Array.from({ length: 9 }, (_, i) => ({ value: String(i + 1), label: `Calendário ${i + 1}` })),
]

/** Sentinela da UI -> sufixo que o sidecar/Znuny esperam (`''` = padrão). */
export function calendarToQuery(value: string): string {
  return value === DEFAULT_CALENDAR ? '' : value
}

/** Valida o valor do SELETOR (domínio da UI: `default`, `1`..`9`). */
export function isValidCalendar(value: string): boolean {
  return CALENDAR_OPTIONS.some(o => o.value === value)
}

/** Valida o SUFIXO que vai para o sidecar/Znuny (domínio da API: `''`, `1`..`9`).
 *
 * São dois domínios de verdade, não redundância: a UI nunca pode ter opção com
 * valor vazio (quebra o `USelect` no SSR), e a API nunca aceita `default` — o
 * calendário padrão do Znuny é o sufixo ausente. Misturar os dois foi o que
 * derrubou a tela. */
export function isValidCalendarSuffix(value: string): boolean {
  return value === '' || /^[1-9]$/.test(value)
}

// ---- Conversão grade <-> payload do Znuny (TimeWorkingHours) --------------

export type WorkingHoursPayload = Record<string, number[]>

export function gridToPayload(grid: WorkingGrid): WorkingHoursPayload {
  const out: WorkingHoursPayload = {}
  for (const day of DAY_KEYS) {
    const hours = grid[day]
      .map((on, hour) => (on ? hour : -1))
      .filter(h => h >= 0)
    if (hours.length > 0) out[day] = hours
  }
  return out
}

// Tolerante: dia desconhecido é ignorado, hora fora de 0-23 é descartada.
// Não é o guardião da forma (isso é validateWorkingHoursShape) — só evita
// que um payload estranho quebre a renderização da grade.
export function payloadToGrid(payload: WorkingHoursPayload | null | undefined): WorkingGrid {
  const grid = emptyGrid()
  if (!payload) return grid
  for (const day of DAY_KEYS) {
    const hours = payload[day]
    if (!Array.isArray(hours)) continue
    for (const h of hours) {
      if (Number.isInteger(h) && h >= 0 && h <= 23) grid[day]![h] = true
    }
  }
  return grid
}

export function weeklyTotalHours(grid: WorkingGrid): number {
  return DAY_KEYS.reduce((sum, day) => sum + grid[day].filter(Boolean).length, 0)
}

// ---- Edição da grade --------------------------------------------------

export function setCell(grid: WorkingGrid, day: DayKey, hour: number, value: boolean): WorkingGrid {
  const next = cloneGrid(grid)
  if (hour >= 0 && hour <= 23) next[day]![hour] = value
  return next
}

// Faixa dentro do mesmo dia (clique + shift-clique, ou arrasto horizontal).
export function toggleHourRange(grid: WorkingGrid, day: DayKey, fromHour: number, toHour: number, value: boolean): WorkingGrid {
  const next = cloneGrid(grid)
  const lo = Math.max(0, Math.min(fromHour, toHour))
  const hi = Math.min(23, Math.max(fromHour, toHour))
  for (let h = lo; h <= hi; h++) next[day]![h] = value
  return next
}

function cloneGrid(grid: WorkingGrid): WorkingGrid {
  const next = {} as WorkingGrid
  for (const day of DAY_KEYS) next[day] = [...grid[day]]
  return next
}

// ---- Atalhos ------------------------------------------------------------

export type ShortcutKey = 'business' | 'all' | 'clear'

export const SHORTCUTS: { key: ShortcutKey, label: string }[] = [
  { key: 'business', label: 'Comercial 8–18, seg a sex' },
  { key: 'all', label: '24/7' },
  { key: 'clear', label: 'Limpar' },
]

const BUSINESS_DAYS: DayKey[] = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
// "8–18" = das 8h às 18h, ou seja, as horas cheias 8..17 estão ocupadas.
const BUSINESS_HOURS = Array.from({ length: 10 }, (_, i) => i + 8) // 8..17

export function applyShortcut(shortcut: ShortcutKey): WorkingGrid {
  const grid = emptyGrid()
  if (shortcut === 'clear') return grid
  if (shortcut === 'all') {
    for (const day of DAY_KEYS) grid[day] = grid[day].map(() => true)
    return grid
  }
  // business
  for (const day of BUSINESS_DAYS) {
    for (const h of BUSINESS_HOURS) grid[day]![h] = true
  }
  return grid
}

// ---- Validação de forma (espelho do 422 do sidecar) ------------------

export function validateWorkingHoursShape(payload: unknown): string[] {
  const errors: string[] = []
  if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) {
    return ['Jornada de trabalho precisa ser um objeto com um dia da semana por chave.']
  }
  const obj = payload as Record<string, unknown>
  for (const [day, hours] of Object.entries(obj)) {
    if (!DAY_KEYS.includes(day as DayKey)) {
      errors.push(`Dia da semana desconhecido: "${day}".`)
      continue
    }
    if (!Array.isArray(hours)) {
      errors.push(`${DAY_LABELS[day as DayKey]}: precisa ser uma lista de horas.`)
      continue
    }
    for (const h of hours) {
      if (!Number.isInteger(h) || h < 0 || h > 23) {
        errors.push(`${DAY_LABELS[day as DayKey]}: hora inválida "${String(h)}" (precisa ser 0–23).`)
      }
    }
  }
  return errors
}

// =====================================================================
// Feriados
// =====================================================================

export interface RecurringHoliday {
  month: number // 1-12
  day: number // 1-31
  description: string
}

export interface OneTimeHoliday {
  year: number
  month: number // 1-12
  day: number // 1-31
  description: string
}

export const MONTH_LABELS: string[] = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
]

export function monthLabel(month: number): string {
  return MONTH_LABELS[month - 1] ?? `Mês ${month}`
}

const DAYS_IN_MONTH = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31] // fev com margem p/ bissexto

export function isValidMonth(month: number): boolean {
  return Number.isInteger(month) && month >= 1 && month <= 12
}

export function isValidDayOfMonth(month: number, day: number): boolean {
  if (!Number.isInteger(day) || day < 1) return false
  const max = isValidMonth(month) ? DAYS_IN_MONTH[month - 1]! : 31
  return day <= max
}

export function emptyRecurringHoliday(): RecurringHoliday {
  return { month: 1, day: 1, description: '' }
}

export function emptyOneTimeHoliday(): OneTimeHoliday {
  const year = new Date().getFullYear()
  return { year, month: 1, day: 1, description: '' }
}

export function validateRecurringHoliday(h: RecurringHoliday): string[] {
  const errors: string[] = []
  if (!isValidMonth(h.month)) errors.push('Mês inválido.')
  if (!isValidDayOfMonth(h.month, h.day)) errors.push('Dia inválido para o mês informado.')
  if (!h.description.trim()) errors.push('Descrição é obrigatória.')
  else if (h.description.trim().length > 200) errors.push('Descrição precisa ter até 200 caracteres.')
  return errors
}

export function validateOneTimeHoliday(h: OneTimeHoliday): string[] {
  const errors: string[] = []
  if (!Number.isInteger(h.year) || h.year < 2000 || h.year > 2100) errors.push('Ano inválido.')
  if (!isValidMonth(h.month)) errors.push('Mês inválido.')
  if (!isValidDayOfMonth(h.month, h.day)) errors.push('Dia inválido para o mês informado.')
  if (!h.description.trim()) errors.push('Descrição é obrigatória.')
  else if (h.description.trim().length > 200) errors.push('Descrição precisa ter até 200 caracteres.')
  return errors
}

// Valida a FORMA crua do payload (antes da conversão tolerante acima, que
// descarta silenciosamente chave inválida — aqui é o contrário: toda chave
// fora do esperado vira erro explícito, espelhando a guarda #2 do Bloco D
// ("forma errada -> 422, sem tocar no Znuny").
export function validateRecurringDaysShape(payload: unknown): string[] {
  const errors: string[] = []
  if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) {
    return ['Feriados recorrentes precisam ser um objeto no formato mês -> dia -> descrição.']
  }
  for (const [monthKey, days] of Object.entries(payload as Record<string, unknown>)) {
    const month = Number(monthKey)
    if (!isValidMonth(month)) {
      errors.push(`Mês inválido em feriados recorrentes: "${monthKey}".`)
      continue
    }
    if (days === null || typeof days !== 'object' || Array.isArray(days)) {
      errors.push(`${monthLabel(month)}: precisa ser um objeto no formato dia -> descrição.`)
      continue
    }
    for (const [dayKey, desc] of Object.entries(days as Record<string, unknown>)) {
      const day = Number(dayKey)
      if (!isValidDayOfMonth(month, day)) errors.push(`${monthLabel(month)}: dia inválido "${dayKey}".`)
      if (typeof desc !== 'string' || !desc.trim()) errors.push(`${monthLabel(month)}, dia ${dayKey}: descrição é obrigatória.`)
    }
  }
  return errors
}

export function validateOneTimeDaysShape(payload: unknown): string[] {
  const errors: string[] = []
  if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) {
    return ['Feriados de data específica precisam ser um objeto no formato ano -> mês -> dia -> descrição.']
  }
  for (const [yearKey, months] of Object.entries(payload as Record<string, unknown>)) {
    const year = Number(yearKey)
    if (!Number.isInteger(year) || year < 2000 || year > 2100) {
      errors.push(`Ano inválido em feriados de data específica: "${yearKey}".`)
      continue
    }
    if (months === null || typeof months !== 'object' || Array.isArray(months)) {
      errors.push(`${yearKey}: precisa ser um objeto no formato mês -> dia -> descrição.`)
      continue
    }
    for (const [monthKey, days] of Object.entries(months as Record<string, unknown>)) {
      const month = Number(monthKey)
      if (!isValidMonth(month)) {
        errors.push(`${yearKey}: mês inválido "${monthKey}".`)
        continue
      }
      if (days === null || typeof days !== 'object' || Array.isArray(days)) {
        errors.push(`${yearKey}, ${monthLabel(month)}: precisa ser um objeto no formato dia -> descrição.`)
        continue
      }
      for (const [dayKey, desc] of Object.entries(days as Record<string, unknown>)) {
        const day = Number(dayKey)
        if (!isValidDayOfMonth(month, day)) errors.push(`${yearKey}, ${monthLabel(month)}: dia inválido "${dayKey}".`)
        if (typeof desc !== 'string' || !desc.trim()) errors.push(`${yearKey}, ${monthLabel(month)}, dia ${dayKey}: descrição é obrigatória.`)
      }
    }
  }
  return errors
}

export function isRecurringHolidayValid(h: RecurringHoliday): boolean {
  return validateRecurringHoliday(h).length === 0
}

export function isOneTimeHolidayValid(h: OneTimeHoliday): boolean {
  return validateOneTimeHoliday(h).length === 0
}

// ---- Conversão listas <-> payload do Znuny --------------------------

export type RecurringPayload = Record<string, Record<string, string>> // mês -> dia -> texto
export type OneTimePayload = Record<string, Record<string, Record<string, string>>> // ano -> mês -> dia -> texto

export function recurringToPayload(list: RecurringHoliday[]): RecurringPayload {
  const out: RecurringPayload = {}
  for (const h of list) {
    const m = String(h.month)
    out[m] ??= {}
    out[m]![String(h.day)] = h.description.trim()
  }
  return out
}

export function payloadToRecurring(payload: RecurringPayload | null | undefined): RecurringHoliday[] {
  const out: RecurringHoliday[] = []
  if (!payload) return out
  for (const [monthKey, days] of Object.entries(payload)) {
    const month = Number(monthKey)
    if (!isValidMonth(month) || typeof days !== 'object' || days === null) continue
    for (const [dayKey, description] of Object.entries(days)) {
      const day = Number(dayKey)
      if (!isValidDayOfMonth(month, day)) continue
      out.push({ month, day, description: String(description ?? '') })
    }
  }
  return out
}

export function oneTimeToPayload(list: OneTimeHoliday[]): OneTimePayload {
  const out: OneTimePayload = {}
  for (const h of list) {
    const y = String(h.year)
    const m = String(h.month)
    out[y] ??= {}
    out[y]![m] ??= {}
    out[y]![m]![String(h.day)] = h.description.trim()
  }
  return out
}

export function payloadToOneTime(payload: OneTimePayload | null | undefined): OneTimeHoliday[] {
  const out: OneTimeHoliday[] = []
  if (!payload) return out
  for (const [yearKey, months] of Object.entries(payload)) {
    const year = Number(yearKey)
    if (!Number.isInteger(year) || typeof months !== 'object' || months === null) continue
    for (const [monthKey, days] of Object.entries(months)) {
      const month = Number(monthKey)
      if (!isValidMonth(month) || typeof days !== 'object' || days === null) continue
      for (const [dayKey, description] of Object.entries(days)) {
        const day = Number(dayKey)
        if (!isValidDayOfMonth(month, day)) continue
        out.push({ year, month, day, description: String(description ?? '') })
      }
    }
  }
  return out
}

// ---- Ordenação e agrupamento (a UI mostra por data, agrupado por mês) ----

export function sortRecurring(list: RecurringHoliday[]): RecurringHoliday[] {
  return [...list].sort((a, b) => a.month - b.month || a.day - b.day)
}

export function sortOneTime(list: OneTimeHoliday[]): OneTimeHoliday[] {
  return [...list].sort((a, b) => a.year - b.year || a.month - b.month || a.day - b.day)
}

export interface HolidayGroup<T> {
  key: string
  label: string
  items: T[]
}

export function groupRecurringByMonth(list: RecurringHoliday[]): HolidayGroup<RecurringHoliday>[] {
  const sorted = sortRecurring(list)
  const groups: HolidayGroup<RecurringHoliday>[] = []
  for (const h of sorted) {
    const key = String(h.month)
    let group = groups.find(g => g.key === key)
    if (!group) {
      group = { key, label: monthLabel(h.month), items: [] }
      groups.push(group)
    }
    group.items.push(h)
  }
  return groups
}

export function groupOneTimeByMonth(list: OneTimeHoliday[]): HolidayGroup<OneTimeHoliday>[] {
  const sorted = sortOneTime(list)
  const groups: HolidayGroup<OneTimeHoliday>[] = []
  for (const h of sorted) {
    const key = `${h.year}-${h.month}`
    let group = groups.find(g => g.key === key)
    if (!group) {
      group = { key, label: `${monthLabel(h.month)} de ${h.year}`, items: [] }
      groups.push(group)
    }
    group.items.push(h)
  }
  return groups
}

// =====================================================================
// Payload completo enviado/recebido do proxy (/api/admin/znuny/calendar)
// =====================================================================

export interface CalendarPayload {
  calendar: string // '' = padrão, '1'..'9' = Calendar1..9
  time_working_hours: WorkingHoursPayload
  time_vacation_days: RecurringPayload
  time_vacation_days_one_time: OneTimePayload
}

export function validateCalendarPayload(payload: CalendarPayload): string[] {
  const errors: string[] = []
  if (!isValidCalendarSuffix(payload.calendar)) errors.push('Calendário selecionado é inválido.')
  errors.push(...validateWorkingHoursShape(payload.time_working_hours))
  errors.push(...validateRecurringDaysShape(payload.time_vacation_days))
  errors.push(...validateOneTimeDaysShape(payload.time_vacation_days_one_time))
  return errors
}

// ---- Resumo de mudanças para a confirmação antes de salvar ------------
// O operador confere isto antes de gravar no Znuny: quantas horas semanais
// mudam e quantos feriados foram adicionados/removidos/alterados.

export interface CalendarChangeSummary {
  weeklyHoursBefore: number
  weeklyHoursAfter: number
  weeklyHoursChanged: boolean
  recurringAdded: number
  recurringRemoved: number
  recurringChanged: number
  oneTimeAdded: number
  oneTimeRemoved: number
  oneTimeChanged: number
}

function diffKeyedHolidays(
  before: Map<string, { description: string }>,
  after: Map<string, { description: string }>,
): { added: number, removed: number, changed: number } {
  let added = 0
  let removed = 0
  let changed = 0
  for (const [key, a] of after) {
    const b = before.get(key)
    if (!b) added++
    else if (b.description !== a.description) changed++
  }
  for (const key of before.keys()) {
    if (!after.has(key)) removed++
  }
  return { added, removed, changed }
}

export function summarizeCalendarChanges(before: CalendarPayload, after: CalendarPayload): CalendarChangeSummary {
  const weeklyHoursBefore = weeklyTotalHours(payloadToGrid(before.time_working_hours))
  const weeklyHoursAfter = weeklyTotalHours(payloadToGrid(after.time_working_hours))

  const recurringBefore = new Map(payloadToRecurring(before.time_vacation_days).map(h => [`${h.month}-${h.day}`, h]))
  const recurringAfter = new Map(payloadToRecurring(after.time_vacation_days).map(h => [`${h.month}-${h.day}`, h]))
  const recurringDiff = diffKeyedHolidays(recurringBefore, recurringAfter)

  const oneTimeBefore = new Map(payloadToOneTime(before.time_vacation_days_one_time).map(h => [`${h.year}-${h.month}-${h.day}`, h]))
  const oneTimeAfter = new Map(payloadToOneTime(after.time_vacation_days_one_time).map(h => [`${h.year}-${h.month}-${h.day}`, h]))
  const oneTimeDiff = diffKeyedHolidays(oneTimeBefore, oneTimeAfter)

  return {
    weeklyHoursBefore,
    weeklyHoursAfter,
    weeklyHoursChanged: weeklyHoursBefore !== weeklyHoursAfter,
    recurringAdded: recurringDiff.added,
    recurringRemoved: recurringDiff.removed,
    recurringChanged: recurringDiff.changed,
    oneTimeAdded: oneTimeDiff.added,
    oneTimeRemoved: oneTimeDiff.removed,
    oneTimeChanged: oneTimeDiff.changed,
  }
}

// ---- Erros vindos do sidecar (422) -----------------------------------
// `ZnunyWriteError` chega como string (mensagem do Znuny/GI); erro de forma
// (Pydantic) chega como array de {loc, msg}. Convertemos os dois em uma
// lista de frases legíveis — nunca mostramos o JSON cru.
export function parseCalendarErrors(detail: unknown): string[] {
  if (Array.isArray(detail)) {
    return detail.map((d) => {
      const entry = d as { loc?: unknown[], msg?: unknown }
      const loc = Array.isArray(entry.loc) ? entry.loc.filter(p => p !== 'body').join(' → ') : ''
      const msg = String(entry.msg ?? 'Valor inválido.')
      return loc ? `${loc}: ${msg}` : msg
    })
  }
  if (typeof detail === 'string' && detail) return [detail]
  return ['O sidecar recusou a gravação, sem detalhar o motivo. Nada foi alterado.']
}
