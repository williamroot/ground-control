// Agenda de atividades recorrentes (T-R11.4/11.5, R11). Lógica PURA.
//
// *"É uma agenda. Isso é importante também, porque é o dia a dia dos
// técnicos."* (07:09)

export type Frequency = 'once' | 'weekly' | 'monthly'

export interface RecurringTask {
  id: string
  title: string
  body: string
  frequency: Frequency
  weekday: number | null
  day_of_month: number | null
  at_time: string
  starts_on: string
  ends_on: string | null
  znuny_queue_name: string | null
  service: string | null
  type: string | null
  priority: string | null
  customer_user_login: string
  contract_id: string | null
  active: boolean
  schedule_label: string
  next_occurrence: string | null
  last_ticket_id: number | null
}

export interface AgendaEntry {
  task_id: string
  title: string
  date: string
  schedule_label: string
  znuny_ticket_id: number | null
}

export interface RecurringDraft {
  title: string
  body: string
  frequency: Frequency
  weekday: number | null
  day_of_month: number | null
  at_time: string
  starts_on: string
  ends_on: string
  znuny_queue_name: string
  customer_user_login: string
  contract_id: string
  active: boolean
}

export const WEEKDAYS = [
  { label: 'Segunda-feira', value: 0 },
  { label: 'Terça-feira', value: 1 },
  { label: 'Quarta-feira', value: 2 },
  { label: 'Quinta-feira', value: 3 },
  { label: 'Sexta-feira', value: 4 },
  { label: 'Sábado', value: 5 },
  { label: 'Domingo', value: 6 },
]

export const FREQUENCIES = [
  { label: 'Uma vez', value: 'once' },
  { label: 'Toda semana', value: 'weekly' },
  { label: 'Todo mês', value: 'monthly' },
]

// O texto que resolve a suposição S4 na tela: preventiva NÃO consome contrato
// por padrão. Sem isto escrito, a escolha vira surpresa na primeira fatura.
export const CONTRACT_HINT
  = 'Deixe em branco para a atividade NÃO consumir saldo do cliente — é o padrão '
    + 'para manutenção preventiva. Vincule um contrato só se as horas devem ser faturadas.'

export function emptyRecurringDraft(): RecurringDraft {
  return {
    title: '',
    body: '',
    frequency: 'weekly',
    weekday: 0,
    day_of_month: null,
    at_time: '08:00',
    starts_on: new Date().toISOString().slice(0, 10),
    ends_on: '',
    znuny_queue_name: '',
    customer_user_login: '',
    contract_id: '',
    active: true,
  }
}

export function draftFromTask(t: RecurringTask): RecurringDraft {
  return {
    title: t.title,
    body: t.body,
    frequency: t.frequency,
    weekday: t.weekday,
    day_of_month: t.day_of_month,
    at_time: t.at_time,
    starts_on: t.starts_on,
    ends_on: t.ends_on ?? '',
    znuny_queue_name: t.znuny_queue_name ?? '',
    customer_user_login: t.customer_user_login,
    contract_id: t.contract_id ?? '',
    active: t.active,
  }
}

/** Erros em português. Lista vazia = pode salvar. */
export function validateRecurringDraft(d: RecurringDraft): string[] {
  const errors: string[] = []
  if (!d.title.trim()) errors.push('Título é obrigatório.')
  if (!d.customer_user_login.trim()) errors.push('Escolha quem figura como solicitante.')
  if (!d.starts_on) errors.push('Data de início é obrigatória.')
  if (d.frequency === 'weekly' && d.weekday === null) errors.push('Escolha o dia da semana.')
  if (d.frequency === 'monthly' && !d.day_of_month) errors.push('Escolha o dia do mês.')
  if (d.ends_on && d.starts_on && d.ends_on < d.starts_on) {
    errors.push('A data final é anterior à inicial.')
  }
  if (!/^\d{2}:\d{2}$/.test(d.at_time)) errors.push('Horário no formato HH:MM.')
  return errors
}

export function buildRecurringPayload(d: RecurringDraft): Record<string, unknown> {
  return {
    title: d.title.trim(),
    body: d.body.trim(),
    frequency: d.frequency,
    // O campo que não pertence à frequência escolhida vai NULO — mandar os
    // dois deixaria o cadastro ambíguo e o CHECK do banco recusaria.
    weekday: d.frequency === 'weekly' ? d.weekday : null,
    day_of_month: d.frequency === 'monthly' ? d.day_of_month : null,
    at_time: `${d.at_time}:00`,
    starts_on: d.starts_on,
    ends_on: d.ends_on || null,
    znuny_queue_name: d.znuny_queue_name.trim() || null,
    customer_user_login: d.customer_user_login.trim(),
    contract_id: d.contract_id || null,
    active: d.active,
  }
}

/** Aviso do dia 29-31: a tela precisa dizer o que acontece em fevereiro. */
export function shortMonthWarning(d: RecurringDraft): string | null {
  if (d.frequency !== 'monthly' || !d.day_of_month || d.day_of_month <= 28) return null
  return `Em meses mais curtos, a atividade cai no último dia do mês (dia ${d.day_of_month} não existe em fevereiro).`
}

/** Agrupa a agenda por data — é como o técnico lê uma semana. */
export function groupAgendaByDate(entries: AgendaEntry[]): { date: string, items: AgendaEntry[] }[] {
  const byDate = new Map<string, AgendaEntry[]>()
  for (const e of entries) {
    const list = byDate.get(e.date) ?? []
    list.push(e)
    byDate.set(e.date, list)
  }
  return [...byDate.entries()].sort((a, b) => a[0].localeCompare(b[0]))
    .map(([date, items]) => ({ date, items }))
}
