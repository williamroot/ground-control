// Correções do teste "TESTE_Znuny-V01" (docs/superpowers/plans/
// 2026-10-07-correcoes-teste-znuny-v01.md) — a parte que é lógica pura e os
// três proxies novos/usados. O que é layout (rolagem horizontal, carga direta
// de página) é coberto pelo e2e de navegador; aqui fica o que decide rótulo,
// filtro e fallback.
import { getRouterParam } from 'h3'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  CALENDAR_OPTIONS,
  calendarOptionsFromList,
  parseCalendarErrors,
  payloadToGrid,
  weeklyTotalHours,
} from '../composables/useWorkingHours'
import {
  billingCycleLabel,
  billingCycleOptions,
  formatIsoDate,
  type BillingCycleOption,
} from '../composables/useBilling'
import {
  agentDisplayName,
  agentSelectOptions,
  normalizeZnunyAgents,
  sidecarErrorMessage,
  type AgentLicense,
} from '../composables/useLicensing'
import calendarsHandler from '../server/api/admin/znuny/calendars.get'
import billingCyclesHandler from '../server/api/admin/tenants/[id]/billing-cycles.get'

// Intl usa espaço não separável em "R$ 160,00"; compara com espaço comum.
const plain = (s: string) => s.replace(/\u00A0/g, ' ')

// ---- Proxies ---------------------------------------------------------------

interface FakeEvent {
  context: { params: Record<string, string> }
  node: { req: { headers: Record<string, string> }, res: { statusCode?: number } }
}
function makeEvent(params: Record<string, string> = {}): FakeEvent {
  return { context: { params }, node: { req: { headers: {} }, res: {} } }
}
function stubSidecar(impl: (path: string) => { status: number, data: unknown }) {
  Object.assign(globalThis, {
    sidecarFetch: (_e: unknown, path: string) => Promise.resolve({ ...impl(path), setCookie: [] }),
  })
}
beforeEach(() => {
  // Auto-import do Nitro em produção; o h3 real lê `event.context.params`.
  Object.assign(globalThis, { getRouterParam })
})
afterEach(() => {
  Object.assign(globalThis, {
    sidecarFetch: () => Promise.resolve({ status: 500, data: null, setCookie: [] }),
  })
})

describe('proxy GET /api/admin/znuny/calendars', () => {
  it('repassa a lista do sidecar', async () => {
    let seen = ''
    const list = [{ value: 'default', name: null }, { value: '3', name: 'Feriados de São Paulo' }]
    stubSidecar((path) => { seen = path; return { status: 200, data: list } })
    const res = await calendarsHandler(makeEvent() as never)
    expect(seen).toBe('/v1/admin/znuny/calendars')
    expect(res).toEqual(list)
  })

  it('falha do sidecar vira null (a tela cai nos rótulos estáticos)', async () => {
    stubSidecar(() => ({ status: 503, data: { detail: 'znuny_unavailable' } }))
    expect(await calendarsHandler(makeEvent() as never)).toBeNull()
  })
})

describe('proxy GET /api/admin/tenants/:id/billing-cycles', () => {
  it('pede só os ciclos sem fatura, do tenant da rota', async () => {
    let seen = ''
    stubSidecar((path) => { seen = path; return { status: 200, data: [] } })
    const res = await billingCyclesHandler(makeEvent({ id: 'abc-123' }) as never)
    expect(seen).toBe('/v1/admin/tenants/abc-123/billing-cycles?uninvoiced=true')
    expect(res).toEqual([])
  })

  it('id com barra não escapa da rota do tenant', async () => {
    let seen = ''
    stubSidecar((path) => { seen = path; return { status: 200, data: [] } })
    await billingCyclesHandler(makeEvent({ id: '../outro' }) as never)
    expect(seen).toBe('/v1/admin/tenants/..%2Foutro/billing-cycles?uninvoiced=true')
  })

  it('404/401 do sidecar vira null', async () => {
    stubSidecar(() => ({ status: 404, data: { detail: 'tenant_not_found' } }))
    expect(await billingCyclesHandler(makeEvent({ id: 'x' }) as never)).toBeNull()
  })
})

// ---- T5 — calendário --------------------------------------------------------

describe('calendarOptionsFromList (E1)', () => {
  it('põe o nome gravado no rótulo', () => {
    const opts = calendarOptionsFromList([
      { value: 'default', name: null },
      { value: '3', name: 'Feriados de São Paulo' },
    ])
    expect(opts.find(o => o.value === '3')?.label).toBe('Calendário 3 — Feriados de São Paulo')
    expect(opts.find(o => o.value === 'default')?.label).toBe('Padrão')
    expect(opts.find(o => o.value === '4')?.label).toBe('Calendário 4')
  })

  it('lista que falhou devolve os 10 rótulos estáticos', () => {
    expect(calendarOptionsFromList(null)).toEqual(CALENDAR_OPTIONS)
    expect(calendarOptionsFromList({ detail: 'x' })).toEqual(CALENDAR_OPTIONS)
  })

  it('lista parcial não some com opção nenhuma, e na ordem fixa', () => {
    const opts = calendarOptionsFromList([{ value: '9', name: 'Filial' }])
    expect(opts.map(o => o.value)).toEqual(CALENDAR_OPTIONS.map(o => o.value))
  })

  it('ignora valor fora do domínio e nome que não é texto', () => {
    const opts = calendarOptionsFromList([
      { value: '10', name: 'x' },
      { value: '', name: 'vazio' },
      { value: '2', name: 42 },
      null,
    ])
    expect(opts).toHaveLength(10)
    expect(opts.find(o => o.value === '2')?.label).toBe('Calendário 2')
    expect(opts.some(o => o.value === '' || o.value === '10')).toBe(false)
  })

  it('nome só com espaços não vira "Calendário 5 — "', () => {
    const opts = calendarOptionsFromList([{ value: '5', name: '   ' }])
    expect(opts.find(o => o.value === '5')?.label).toBe('Calendário 5')
  })
})

// ---- T2 — faturas -----------------------------------------------------------

const cycle = (over: Partial<BillingCycleOption> = {}): BillingCycleOption => ({
  id: 'c1',
  contract_id: 'k1',
  contract_code: 'AUR-PACOTE-2026',
  period_start: '2026-09-01',
  period_end: '2026-09-30',
  total_cents: 16000,
  ...over,
})

describe('formatIsoDate', () => {
  it('não recua um dia no fuso do Brasil', () => {
    // new Date('2026-09-01') é meia-noite UTC = 31/08 em São Paulo.
    expect(formatIsoDate('2026-09-01')).toBe('01/09/2026')
    expect(formatIsoDate('2026-09-30T00:00:00Z')).toBe('30/09/2026')
  })

  it('valor inesperado volta como veio', () => {
    expect(formatIsoDate('ontem')).toBe('ontem')
    expect(formatIsoDate(null)).toBe('')
  })
})

describe('billingCycleLabel (B5)', () => {
  it('período · contrato · valor', () => {
    expect(plain(billingCycleLabel(cycle()))).toBe('01/09/2026 – 30/09/2026 · AUR-PACOTE-2026 · R$ 160,00')
  })

  it('sem valor quando total_cents é null', () => {
    expect(billingCycleLabel(cycle({ total_cents: null }))).toBe('01/09/2026 – 30/09/2026 · AUR-PACOTE-2026')
  })

  it('zero é valor, não ausência', () => {
    expect(plain(billingCycleLabel(cycle({ total_cents: 0 })))).toContain('R$ 0,00')
  })
})

describe('billingCycleOptions', () => {
  it('lista vazia ou falha → nenhuma opção', () => {
    expect(billingCycleOptions([])).toEqual([])
    expect(billingCycleOptions(null)).toEqual([])
  })

  it('ordena pelo período, value é o id do ciclo', () => {
    const opts = billingCycleOptions([
      cycle({ id: 'out', period_start: '2026-10-01', period_end: '2026-10-31' }),
      cycle({ id: 'set' }),
    ])
    expect(opts.map(o => o.value)).toEqual(['set', 'out'])
  })
})

// ---- T6 — licenças ----------------------------------------------------------

const license = (agent_login: string, active = true): AgentLicense => ({
  agent_login,
  active,
  modules: ['tickets'],
  assigned_at: '2026-08-19T00:00:00Z',
  assigned_by: null,
  revoked_at: active ? null : '2026-09-01T00:00:00Z',
})

describe('normalizeZnunyAgents (F5)', () => {
  it('lê a lista do sidecar e descarta agente inválido', () => {
    const out = normalizeZnunyAgents([
      { id: 1, login: 'william', first_name: 'William', last_name: 'Souza', email: 'w@x', valid: true },
      { id: 2, login: 'bruno.cardoso', first_name: 'Bruno', last_name: 'Cardoso', email: 'b@x', valid: true },
      { id: 3, login: 'antigo', first_name: 'Ex', last_name: 'Agente', email: 'e@x', valid: false },
    ])
    expect(out).toEqual([
      { login: 'william', name: 'William Souza' },
      { login: 'bruno.cardoso', name: 'Bruno Cardoso' },
    ])
  })

  it('aceita o envelope { items } com as chaves do Znuny', () => {
    const out = normalizeZnunyAgents({
      items: [
        { UserID: 5, UserLogin: 'diego.fontana', UserFirstname: 'Diego', UserLastname: 'Fontana', ValidID: 1 },
        { UserID: 6, UserLogin: 'x', UserFirstname: 'X', UserLastname: 'Y', ValidID: '2' },
      ],
    })
    expect(out).toEqual([{ login: 'diego.fontana', name: 'Diego Fontana' }])
  })

  it('resposta nula ou estranha → nenhum agente', () => {
    expect(normalizeZnunyAgents(null)).toEqual([])
    expect(normalizeZnunyAgents({ detail: 'x' })).toEqual([])
    expect(normalizeZnunyAgents([{ login: '' }, 'william'])).toEqual([])
  })
})

describe('agentSelectOptions', () => {
  const agents = [
    { login: 'patricia.menezes', name: 'Patrícia Menezes' },
    { login: 'bruno.cardoso', name: 'Bruno Cardoso' },
    { login: 'semnome', name: '' },
  ]

  it('rótulo "Nome (login)", ordenado pelo nome', () => {
    const opts = agentSelectOptions(agents, [])
    expect(opts.map(o => o.label)).toEqual([
      'Bruno Cardoso (bruno.cardoso)',
      'Patrícia Menezes (patricia.menezes)',
      'semnome',
    ])
    expect(opts[0]!.value).toBe('bruno.cardoso')
  })

  it('quem já tem licença ativa fica marcado; revogada não', () => {
    const opts = agentSelectOptions(agents, [license('bruno.cardoso'), license('patricia.menezes', false)])
    expect(opts.find(o => o.value === 'bruno.cardoso')?.label).toBe('Bruno Cardoso (bruno.cardoso) · já licenciado')
    expect(opts.find(o => o.value === 'patricia.menezes')?.label).toBe('Patrícia Menezes (patricia.menezes)')
  })

  it('licença fantasma não entra na lista…', () => {
    const opts = agentSelectOptions(agents, [license('georgia')])
    expect(opts.some(o => o.value === 'georgia')).toBe(false)
  })

  it('…a não ser a que está sendo editada, marcada como inexistente', () => {
    const opts = agentSelectOptions(agents, [license('georgia')], 'georgia')
    expect(opts[0]).toEqual({ value: 'georgia', label: 'georgia · não existe no Znuny' })
  })

  it('agentDisplayName', () => {
    expect(agentDisplayName({ login: 'william', name: 'William Souza' })).toBe('William Souza (william)')
    expect(agentDisplayName({ login: 'william', name: '' })).toBe('william')
  })
})

describe('sidecarErrorMessage — o 422 aparece como veio', () => {
  it('detail string', () => {
    const err = { statusCode: 422, data: { detail: 'Agente "georgia" não existe no Znuny.' } }
    expect(sidecarErrorMessage(err)).toBe('Agente "georgia" não existe no Znuny.')
  })

  it('validação do FastAPI (lista)', () => {
    const err = { data: { detail: [{ msg: 'campo obrigatório' }, { msg: 'módulo inválido' }] } }
    expect(sidecarErrorMessage(err)).toBe('campo obrigatório módulo inválido')
  })

  it('sem detail → mensagem genérica', () => {
    expect(sidecarErrorMessage(new Error('boom'))).toBe('Falha na operação.')
    expect(sidecarErrorMessage(null, 'Outra.')).toBe('Outra.')
  })
})


describe('payloadToGrid — formato real do Znuny (horas em texto)', () => {
  it('lê ["8","9"] como 8h e 9h, e ignora lixo', () => {
    const grid = payloadToGrid({ Mon: ['8', '9', 'x', '24', '-1'] } as never)
    expect(grid.Mon![8]).toBe(true)
    expect(grid.Mon![9]).toBe(true)
    expect(weeklyTotalHours(grid)).toBe(2)
  })

  it('a jornada comercial que o staging devolve dá 65 h/semana, não 0', () => {
    const horas = Array.from({ length: 13 }, (_, i) => String(i + 8))
    const payload = { Mon: horas, Tue: horas, Wed: horas, Thu: horas, Fri: horas, Sat: [], Sun: [] }
    expect(weeklyTotalHours(payloadToGrid(payload as never))).toBe(65)
  })
})


describe('parseCalendarErrors — recusa do Znuny no meio da gravação', () => {
  it('mostra a mensagem em vez de "sem detalhar o motivo"', () => {
    const out = parseCalendarErrors({
      message: "AdminSysConfigSet: setting 'TimeZone::Calendar3Name' is not in the calendar/journey allowlist.",
      applied: [],
      failed_setting: 'TimeZone::Calendar3Name',
    })
    expect(out).toEqual(["AdminSysConfigSet: setting 'TimeZone::Calendar3Name' is not in the calendar/journey allowlist."])
  })

  it('avisa o que já foi gravado', () => {
    const out = parseCalendarErrors({ message: 'falhou', applied: ['TimeWorkingHours::Calendar3'] })
    expect(out[1]).toContain('TimeWorkingHours::Calendar3')
  })
})
