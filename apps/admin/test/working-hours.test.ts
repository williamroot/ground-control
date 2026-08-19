// Spec #4, Bloco D — calendário do Znuny (jornada de trabalho + feriados).
// Componentes em HTML nativo (sem U*/@nuxt/icon) montam limpo no vitest
// (lição #1M..#1P). Cobre a lógica de verdade (conversão UI <-> SysConfig,
// validação de forma, atalhos, total semanal, diff do resumo de confirmação)
// e a interação dos componentes via data-testid.
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import HoursGrid from '../components/calendar/HoursGrid.vue'
import OneTimeHolidayEditor from '../components/calendar/OneTimeHolidayEditor.vue'
import RecurringHolidayEditor from '../components/calendar/RecurringHolidayEditor.vue'
import {
  applyShortcut,
  calendarLabel,
  emptyGrid,
  gridToPayload,
  groupOneTimeByMonth,
  groupRecurringByMonth,
  isValidCalendar,
  isValidCalendarSuffix,
  oneTimeToPayload,
  parseCalendarErrors,
  payloadToGrid,
  payloadToOneTime,
  payloadToRecurring,
  recurringToPayload,
  setCell,
  sortOneTime,
  sortRecurring,
  summarizeCalendarChanges,
  toggleHourRange,
  validateCalendarPayload,
  validateOneTimeDaysShape,
  validateOneTimeHoliday,
  validateRecurringDaysShape,
  validateRecurringHoliday,
  validateWorkingHoursShape,
  weeklyTotalHours,
  type CalendarPayload,
  type OneTimeHoliday,
  type RecurringHoliday,
  type WorkingGrid,
  DEFAULT_CALENDAR,
  calendarToQuery,
  isValidCalendar,
} from '../composables/useWorkingHours'

describe('grade <-> payload (TimeWorkingHours: dia -> lista de horas)', () => {
  it('grade vazia produz payload vazio', () => {
    expect(gridToPayload(emptyGrid())).toEqual({})
  })

  it('converte grade em payload só com os dias marcados', () => {
    let grid = emptyGrid()
    grid = setCell(grid, 'Mon', 8, true)
    grid = setCell(grid, 'Mon', 9, true)
    grid = setCell(grid, 'Fri', 17, true)
    expect(gridToPayload(grid)).toEqual({ Mon: [8, 9], Fri: [17] })
  })

  it('roundtrip payload -> grade -> payload preserva o conteúdo', () => {
    const payload = { Mon: [8, 9, 10], Wed: [14, 15] }
    const grid = payloadToGrid(payload)
    expect(gridToPayload(grid)).toEqual(payload)
  })

  it('payloadToGrid é tolerante a dia desconhecido e hora fora de faixa', () => {
    const grid = payloadToGrid({ Mon: [8, 30, -1], Xyz: [1] } as never)
    expect(grid.Mon).toEqual(expect.arrayContaining([true]))
    expect(gridToPayload(grid)).toEqual({ Mon: [8] })
  })

  it('payloadToGrid(null/undefined) devolve grade vazia', () => {
    expect(weeklyTotalHours(payloadToGrid(null))).toBe(0)
    expect(weeklyTotalHours(payloadToGrid(undefined))).toBe(0)
  })
})

describe('weeklyTotalHours — o número que o operador confere', () => {
  it('soma todas as horas marcadas na semana', () => {
    let grid = emptyGrid()
    grid = setCell(grid, 'Mon', 8, true)
    grid = setCell(grid, 'Tue', 9, true)
    grid = setCell(grid, 'Tue', 10, true)
    expect(weeklyTotalHours(grid)).toBe(3)
  })
})

describe('setCell / toggleHourRange', () => {
  it('setCell liga/desliga uma hora sem mutar a grade original', () => {
    const grid = emptyGrid()
    const next = setCell(grid, 'Mon', 8, true)
    expect(grid.Mon[8]).toBe(false)
    expect(next.Mon[8]).toBe(true)
  })

  it('toggleHourRange aplica o mesmo valor a toda a faixa, em qualquer ordem', () => {
    const grid = emptyGrid()
    const asc = toggleHourRange(grid, 'Wed', 8, 11, true)
    expect(asc.Wed.slice(8, 12)).toEqual([true, true, true, true])
    const desc = toggleHourRange(grid, 'Wed', 11, 8, true)
    expect(desc.Wed.slice(8, 12)).toEqual([true, true, true, true])
  })

  it('toggleHourRange também desliga em faixa', () => {
    let grid = emptyGrid()
    grid = toggleHourRange(grid, 'Wed', 0, 23, true)
    grid = toggleHourRange(grid, 'Wed', 8, 11, false)
    expect(weeklyTotalHours(grid)).toBe(20)
  })
})

describe('atalhos', () => {
  it('"24/7" liga todas as 168 horas', () => {
    expect(weeklyTotalHours(applyShortcut('all'))).toBe(24 * 7)
  })

  it('"Limpar" desliga tudo', () => {
    expect(weeklyTotalHours(applyShortcut('clear'))).toBe(0)
  })

  it('"Comercial 8–18, seg a sex" liga 10h x 5 dias = 50h, só dias úteis', () => {
    const grid = applyShortcut('business')
    expect(weeklyTotalHours(grid)).toBe(50)
    expect(grid.Sat.some(Boolean)).toBe(false)
    expect(grid.Sun.some(Boolean)).toBe(false)
    expect(grid.Mon.slice(8, 18)).toEqual(Array.from({ length: 10 }, () => true))
  })
})

describe('validateWorkingHoursShape — espelho do 422', () => {
  it('aceita forma válida', () => {
    expect(validateWorkingHoursShape({ Mon: [8, 9], Fri: [17] })).toEqual([])
  })

  it('rejeita payload que não é objeto', () => {
    expect(validateWorkingHoursShape(null).length).toBeGreaterThan(0)
    expect(validateWorkingHoursShape('nope').length).toBeGreaterThan(0)
    expect(validateWorkingHoursShape([1, 2]).length).toBeGreaterThan(0)
  })

  it('rejeita dia desconhecido e hora fora de 0-23', () => {
    const errors = validateWorkingHoursShape({ Segunda: [8], Mon: [24, -1, 3.5] })
    expect(errors.some(e => e.includes('Segunda'))).toBe(true)
    expect(errors.filter(e => e.includes('hora inválida')).length).toBe(3)
  })
})

describe('isValidCalendar', () => {
  it('aceita o sentinela do padrão e Calendar1..9 (domínio da UI)', () => {
    expect(isValidCalendar(DEFAULT_CALENDAR)).toBe(true)
    expect(isValidCalendar('1')).toBe(true)
    expect(isValidCalendar('9')).toBe(true)
  })

  it('o sufixo da API aceita vazio (padrão do Znuny), a UI não', () => {
    expect(isValidCalendarSuffix('')).toBe(true)
    expect(isValidCalendarSuffix('9')).toBe(true)
    expect(isValidCalendarSuffix('default')).toBe(false)
    expect(isValidCalendar('')).toBe(false)
  })

  it('rejeita fora da faixa', () => {
    expect(isValidCalendar('10')).toBe(false)
    expect(isValidCalendar('0')).toBe(false)
    expect(isValidCalendar('abc')).toBe(false)
  })
})

describe('feriados recorrentes (TimeVacationDays: mês -> dia -> texto)', () => {
  const list: RecurringHoliday[] = [
    { month: 12, day: 25, description: 'Natal' },
    { month: 1, day: 1, description: 'Confraternização Universal' },
  ]

  it('roundtrip lista -> payload -> lista preserva o conteúdo', () => {
    const payload = recurringToPayload(list)
    expect(payload).toEqual({
      12: { 25: 'Natal' },
      1: { 1: 'Confraternização Universal' },
    })
    const back = payloadToRecurring(payload)
    expect(back).toHaveLength(2)
    expect(back).toEqual(expect.arrayContaining(list))
  })

  it('sortRecurring ordena por mês e dia', () => {
    expect(sortRecurring(list).map(h => `${h.month}-${h.day}`)).toEqual(['1-1', '12-25'])
  })

  it('groupRecurringByMonth agrupa por mês em ordem', () => {
    const groups = groupRecurringByMonth(list)
    expect(groups.map(g => g.label)).toEqual(['Janeiro', 'Dezembro'])
    expect(groups[0]!.items).toHaveLength(1)
  })

  it('validateRecurringHoliday rejeita mês/dia/descrição inválidos', () => {
    expect(validateRecurringHoliday({ month: 13, day: 1, description: 'x' }).length).toBeGreaterThan(0)
    expect(validateRecurringHoliday({ month: 2, day: 30, description: 'x' }).length).toBeGreaterThan(0)
    expect(validateRecurringHoliday({ month: 1, day: 1, description: '  ' }).length).toBeGreaterThan(0)
    expect(validateRecurringHoliday({ month: 1, day: 1, description: 'Ano novo' })).toEqual([])
  })
})

describe('feriados de data específica (TimeVacationDaysOneTime: ano -> mês -> dia -> texto)', () => {
  const list: OneTimeHoliday[] = [
    { year: 2026, month: 7, day: 30, description: 'Feriado municipal' },
    { year: 2025, month: 12, day: 24, description: 'Véspera de Natal (ponto facultativo)' },
  ]

  it('roundtrip lista -> payload -> lista preserva o conteúdo', () => {
    const payload = oneTimeToPayload(list)
    expect(payload['2026']!['7']!['30']).toBe('Feriado municipal')
    const back = payloadToOneTime(payload)
    expect(back).toHaveLength(2)
    expect(back).toEqual(expect.arrayContaining(list))
  })

  it('sortOneTime ordena por ano, mês e dia', () => {
    expect(sortOneTime(list).map(h => h.year)).toEqual([2025, 2026])
  })

  it('groupOneTimeByMonth agrupa por ano+mês', () => {
    const groups = groupOneTimeByMonth(list)
    expect(groups.map(g => g.label)).toEqual(['Dezembro de 2025', 'Julho de 2026'])
  })

  it('validateOneTimeHoliday rejeita ano fora de faixa', () => {
    expect(validateOneTimeHoliday({ year: 1999, month: 1, day: 1, description: 'x' }).length).toBeGreaterThan(0)
    expect(validateOneTimeHoliday({ year: 2026, month: 1, day: 1, description: 'Feriado' })).toEqual([])
  })
})

describe('validateRecurringDaysShape / validateOneTimeDaysShape — guarda de forma crua', () => {
  it('recorrente: aceita forma válida', () => {
    expect(validateRecurringDaysShape({ 12: { 25: 'Natal' } })).toEqual([])
  })

  it('recorrente: mês fora da allowlist é erro explícito (não descarta em silêncio)', () => {
    const errors = validateRecurringDaysShape({ 13: { 1: 'x' } })
    expect(errors.length).toBeGreaterThan(0)
    expect(errors[0]).toContain('13')
  })

  it('recorrente: descrição vazia é erro', () => {
    expect(validateRecurringDaysShape({ 1: { 1: '' } }).length).toBeGreaterThan(0)
  })

  it('one-time: aceita forma válida', () => {
    expect(validateOneTimeDaysShape({ 2026: { 7: { 30: 'Feriado municipal' } } })).toEqual([])
  })

  it('one-time: ano fora de faixa é erro explícito', () => {
    const errors = validateOneTimeDaysShape({ 1800: { 1: { 1: 'x' } } })
    expect(errors.length).toBeGreaterThan(0)
  })

  it('one-time: payload que não é objeto é erro', () => {
    expect(validateOneTimeDaysShape('nope').length).toBeGreaterThan(0)
    expect(validateOneTimeDaysShape(null).length).toBeGreaterThan(0)
  })
})

describe('validateCalendarPayload — guarda de forma completa antes de enviar', () => {
  function payload(overrides: Partial<CalendarPayload> = {}): CalendarPayload {
    return {
      calendar: '',
      time_working_hours: { Mon: [8, 9] },
      time_vacation_days: { 1: { 1: 'Ano novo' } },
      time_vacation_days_one_time: {},
      ...overrides,
    }
  }

  it('payload válido não tem erros', () => {
    expect(validateCalendarPayload(payload())).toEqual([])
  })

  it('acumula erros de calendário inválido + jornada + feriado', () => {
    const errors = validateCalendarPayload(payload({
      calendar: '99',
      time_working_hours: { Mon: [30] },
      time_vacation_days: { 13: { 1: 'x' } },
    }))
    expect(errors.length).toBeGreaterThanOrEqual(3)
  })
})

describe('summarizeCalendarChanges — resumo da confirmação antes de salvar', () => {
  const before: CalendarPayload = {
    calendar: '',
    time_working_hours: { Mon: [8, 9, 10] },
    time_vacation_days: { 12: { 25: 'Natal' } },
    time_vacation_days_one_time: {},
  }

  it('sem mudança nenhuma, tudo zerado', () => {
    const s = summarizeCalendarChanges(before, before)
    expect(s.weeklyHoursChanged).toBe(false)
    expect(s.recurringAdded + s.recurringRemoved + s.recurringChanged).toBe(0)
  })

  it('detecta aumento de horas semanais', () => {
    const after: CalendarPayload = { ...before, time_working_hours: { Mon: [8, 9, 10, 11] } }
    const s = summarizeCalendarChanges(before, after)
    expect(s.weeklyHoursBefore).toBe(3)
    expect(s.weeklyHoursAfter).toBe(4)
    expect(s.weeklyHoursChanged).toBe(true)
  })

  it('detecta feriado adicionado, removido e alterado', () => {
    const after: CalendarPayload = {
      ...before,
      time_vacation_days: { 12: { 25: 'Natal (todos os escritórios fechados)' }, 1: { 1: 'Ano novo' } },
    }
    const s = summarizeCalendarChanges(before, after)
    expect(s.recurringAdded).toBe(1) // 1/1
    expect(s.recurringChanged).toBe(1) // 12/25 descrição mudou
    expect(s.recurringRemoved).toBe(0)
  })
})

describe('parseCalendarErrors — nunca mostra o JSON cru do 422', () => {
  it('array de {loc, msg} vira frases legíveis', () => {
    const errors = parseCalendarErrors([
      { loc: ['body', 'time_working_hours', 'Mon', 0], msg: 'hora inválida' },
    ])
    expect(errors[0]).toContain('time_working_hours')
    expect(errors[0]).toContain('hora inválida')
  })

  it('string de domínio (ZnunyWriteError) vira uma frase única', () => {
    expect(parseCalendarErrors('SettingUpdate falhou: valor inválido')).toEqual([
      'SettingUpdate falhou: valor inválido',
    ])
  })

  it('detail ausente/desconhecido não quebra e ainda comunica "nada foi alterado"', () => {
    const errors = parseCalendarErrors(undefined)
    expect(errors.length).toBeGreaterThan(0)
  })
})

describe('HoursGrid — clique, arrasto e atalhos', () => {
  function mountGrid(modelValue: WorkingGrid = emptyGrid()) {
    return mount(HoursGrid, { props: { modelValue } })
  }

  it('clique liga a hora e mostra no total semanal', async () => {
    const wrapper = mountGrid()
    await wrapper.find('[data-testid="hour-cell-Mon-8"]').trigger('mousedown')
    await wrapper.find('[data-testid="hour-cell-Mon-8"]').trigger('mouseup')
    const ev = wrapper.emitted('update:modelValue')!
    const grid = ev.at(-1)![0] as WorkingGrid
    expect(grid.Mon[8]).toBe(true)
    expect(weeklyTotalHours(grid)).toBe(1)
  })

  it('clique de novo na mesma hora desliga (toggle)', async () => {
    let grid = emptyGrid()
    grid = setCell(grid, 'Mon', 8, true)
    const wrapper = mountGrid(grid)
    await wrapper.find('[data-testid="hour-cell-Mon-8"]').trigger('mousedown')
    const ev = wrapper.emitted('update:modelValue')!
    expect((ev.at(-1)![0] as WorkingGrid).Mon[8]).toBe(false)
  })

  it('arrasto (mousedown + mouseenter) pinta várias células com o mesmo valor', async () => {
    // Simula o v-model real: a cada emissão, o "pai" devolve o novo valor via
    // prop antes do próximo evento — senão cada handler leria a grade parada.
    const wrapper = mountGrid()
    await wrapper.find('[data-testid="hour-cell-Tue-9"]').trigger('mousedown')
    await wrapper.setProps({ modelValue: wrapper.emitted('update:modelValue')!.at(-1)![0] as WorkingGrid })
    await wrapper.find('[data-testid="hour-cell-Tue-10"]').trigger('mouseenter')
    await wrapper.setProps({ modelValue: wrapper.emitted('update:modelValue')!.at(-1)![0] as WorkingGrid })
    await wrapper.find('[data-testid="hour-cell-Tue-11"]').trigger('mouseenter')
    const last = wrapper.emitted('update:modelValue')!.at(-1)![0] as WorkingGrid
    expect(last.Tue[9]).toBe(true)
    expect(last.Tue[10]).toBe(true)
    expect(last.Tue[11]).toBe(true)
  })

  it('shift-clique no mesmo dia liga a faixa inteira', async () => {
    const wrapper = mountGrid()
    await wrapper.find('[data-testid="hour-cell-Wed-8"]').trigger('mousedown')
    await wrapper.find('[data-testid="hour-cell-Wed-8"]').trigger('mouseup')
    await wrapper.find('[data-testid="hour-cell-Wed-12"]').trigger('mousedown', { shiftKey: true })
    const ev = wrapper.emitted('update:modelValue')!
    const last = ev.at(-1)![0] as WorkingGrid
    expect(last.Wed.slice(8, 13)).toEqual([true, true, true, true, true])
  })

  it('atalho "24/7" emite grade cheia', async () => {
    const wrapper = mountGrid()
    await wrapper.find('[data-testid="shortcut-all"]').trigger('click')
    const ev = wrapper.emitted('update:modelValue')!
    expect(weeklyTotalHours(ev.at(-1)![0] as WorkingGrid)).toBe(168)
  })

  it('atalho "Comercial" emite 50h', async () => {
    const wrapper = mountGrid()
    await wrapper.find('[data-testid="shortcut-business"]').trigger('click')
    const ev = wrapper.emitted('update:modelValue')!
    expect(weeklyTotalHours(ev.at(-1)![0] as WorkingGrid)).toBe(50)
  })

  it('atalho "Limpar" emite grade vazia', async () => {
    const wrapper = mountGrid(applyShortcut('all'))
    await wrapper.find('[data-testid="shortcut-clear"]').trigger('click')
    const ev = wrapper.emitted('update:modelValue')!
    expect(weeklyTotalHours(ev.at(-1)![0] as WorkingGrid)).toBe(0)
  })

  it('exibe o total semanal atual', () => {
    let grid = emptyGrid()
    grid = setCell(grid, 'Mon', 8, true)
    grid = setCell(grid, 'Mon', 9, true)
    const wrapper = mountGrid(grid)
    expect(wrapper.find('[data-testid="weekly-total"]').text()).toBe('2')
  })
})

describe('RecurringHolidayEditor — adicionar, editar, remover', () => {
  it('adiciona um feriado válido', async () => {
    const wrapper = mount(RecurringHolidayEditor, { props: { modelValue: [] } })
    await wrapper.find('[data-testid="recurring-month"]').setValue('12')
    await wrapper.find('[data-testid="recurring-day"]').setValue('25')
    await wrapper.find('[data-testid="recurring-description"]').setValue('Natal')
    await wrapper.find('[data-testid="recurring-submit"]').trigger('click')
    const ev = wrapper.emitted('update:modelValue')!
    expect(ev.at(-1)![0]).toEqual([{ month: 12, day: 25, description: 'Natal' }])
  })

  it('bloqueia adicionar sem descrição e mostra o erro', async () => {
    const wrapper = mount(RecurringHolidayEditor, { props: { modelValue: [] } })
    await wrapper.find('[data-testid="recurring-day"]').setValue('25')
    await wrapper.find('[data-testid="recurring-submit"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeFalsy()
    expect(wrapper.find('[data-testid="recurring-error"]').exists()).toBe(true)
  })

  it('editar carrega o rascunho e salvar substitui o item', async () => {
    const list: RecurringHoliday[] = [{ month: 1, day: 1, description: 'Ano novo' }]
    const wrapper = mount(RecurringHolidayEditor, { props: { modelValue: list } })
    await wrapper.find('[data-testid="recurring-edit"]').trigger('click')
    expect((wrapper.find('[data-testid="recurring-description"]').element as HTMLInputElement).value).toBe('Ano novo')
    await wrapper.find('[data-testid="recurring-description"]').setValue('Confraternização Universal')
    await wrapper.find('[data-testid="recurring-submit"]').trigger('click')
    const ev = wrapper.emitted('update:modelValue')!
    expect(ev.at(-1)![0]).toEqual([{ month: 1, day: 1, description: 'Confraternização Universal' }])
  })

  it('remover emite a lista sem o item', async () => {
    const list: RecurringHoliday[] = [
      { month: 1, day: 1, description: 'Ano novo' },
      { month: 12, day: 25, description: 'Natal' },
    ]
    const wrapper = mount(RecurringHolidayEditor, { props: { modelValue: list } })
    await wrapper.findAll('[data-testid="recurring-remove"]')[0]!.trigger('click')
    const ev = wrapper.emitted('update:modelValue')!
    expect((ev.at(-1)![0] as RecurringHoliday[])).toHaveLength(1)
  })

  it('sem itens mostra a mensagem de lista vazia', () => {
    const wrapper = mount(RecurringHolidayEditor, { props: { modelValue: [] } })
    expect(wrapper.text()).toContain('Nenhum feriado recorrente cadastrado')
  })
})

describe('OneTimeHolidayEditor — adicionar, editar, remover', () => {
  it('adiciona um feriado válido com ano', async () => {
    const wrapper = mount(OneTimeHolidayEditor, { props: { modelValue: [] } })
    await wrapper.find('[data-testid="onetime-year"]').setValue('2026')
    await wrapper.find('[data-testid="onetime-month"]').setValue('7')
    await wrapper.find('[data-testid="onetime-day"]').setValue('30')
    await wrapper.find('[data-testid="onetime-description"]').setValue('Feriado municipal')
    await wrapper.find('[data-testid="onetime-submit"]').trigger('click')
    const ev = wrapper.emitted('update:modelValue')!
    expect(ev.at(-1)![0]).toEqual([{ year: 2026, month: 7, day: 30, description: 'Feriado municipal' }])
  })

  it('bloqueia ano inválido e mostra o erro', async () => {
    const wrapper = mount(OneTimeHolidayEditor, { props: { modelValue: [] } })
    await wrapper.find('[data-testid="onetime-year"]').setValue('1800')
    await wrapper.find('[data-testid="onetime-description"]').setValue('x')
    await wrapper.find('[data-testid="onetime-submit"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeFalsy()
    expect(wrapper.find('[data-testid="onetime-error"]').exists()).toBe(true)
  })

  it('remover emite a lista sem o item', async () => {
    const list: OneTimeHoliday[] = [{ year: 2026, month: 7, day: 30, description: 'Feriado municipal' }]
    const wrapper = mount(OneTimeHolidayEditor, { props: { modelValue: list } })
    await wrapper.find('[data-testid="onetime-remove"]').trigger('click')
    const ev = wrapper.emitted('update:modelValue')!
    expect(ev.at(-1)![0]).toEqual([])
  })
})

// --------------------------------------------------------------------------- #
// Nenhuma opção de select pode ter valor string vazia.
//
// O `USelect` do Nuxt UI trata string vazia como "sem seleção" e recusa um item
// com esse valor — derrubando a PÁGINA INTEIRA com 500 no SSR. Foi o que
// aconteceu com o calendário "Padrão", cujo sufixo real no Znuny é vazio.
// A UI usa o sentinela `default`; a conversão para o sufixo real acontece só na
// borda da API. Só o navegador pega isso: a rota responde e o endpoint funciona.
// --------------------------------------------------------------------------- #
describe('opções do seletor de calendário', () => {
  it('nenhuma opção tem valor string vazia (quebraria o USelect no SSR)', () => {
    for (const opt of CALENDAR_OPTIONS) {
      expect(opt.value).not.toBe('')
      expect(opt.value.length).toBeGreaterThan(0)
    }
  })

  it('o sentinela do padrão vira sufixo vazio na borda da API', () => {
    expect(calendarToQuery(DEFAULT_CALENDAR)).toBe('')
    expect(calendarToQuery('3')).toBe('3')
  })

  it('o padrão continua sendo uma opção válida', () => {
    expect(isValidCalendar(DEFAULT_CALENDAR)).toBe(true)
    expect(isValidCalendar('')).toBe(false)
  })
})

// ── T-R13.2: o nome do calendário ──────────────────────────────────────────

describe('rótulo do calendário', () => {
  it('usa o nome quando existe', () => {
    // Sem isto a tela de filas mostra "Calendar 3 - " e ninguém sabe qual é
    // o de São Paulo. Era a aresta registrada no levantamento.
    expect(calendarLabel('3', 'Feriados de São Paulo')).toBe('Calendário 3 — Feriados de São Paulo')
  })

  it('cai no número quando não há nome', () => {
    expect(calendarLabel('3', null)).toBe('Calendário 3')
    expect(calendarLabel('3', '   ')).toBe('Calendário 3')
    expect(calendarLabel('3')).toBe('Calendário 3')
  })

  it('o padrão não tem nome — ele é "o calendário"', () => {
    expect(calendarLabel('default')).toBe('Padrão')
    expect(calendarLabel('')).toBe('Padrão')
  })
})
