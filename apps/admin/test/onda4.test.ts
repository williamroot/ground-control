// Onda 4 — lógica pura das telas de agenda (R11) e importação (R8).
//
// Os riscos concretos cobertos aqui:
//   • o campo que não pertence à frequência escolhida ir preenchido, deixando
//     o cadastro ambíguo (e o CHECK do banco recusando com erro feio);
//   • o operador escolher dia 31 e não saber o que acontece em fevereiro;
//   • célula de planilha com `=` virar fórmula ao ser exibida (CSV injection);
//   • o botão "Importar" aparecer antes de simular, ou depois de já ter
//     importado — os dois levam a importar duas vezes.
import { describe, expect, it } from 'vitest'
import {
  buildRecurringPayload,
  draftFromTask,
  emptyRecurringDraft,
  groupAgendaByDate,
  shortMonthWarning,
  validateRecurringDraft,
  type AgendaEntry,
  type RecurringTask,
} from '../composables/useRecurringTasks'
import {
  canRun,
  confirmationLabel,
  safeCell,
  summarize,
  type ImportReport,
} from '../composables/useImport'

// ── agenda ──────────────────────────────────────────────────────────────────

function draft() {
  return {
    ...emptyRecurringDraft(),
    title: 'Verificação de backup',
    customer_user_login: 'mariana.bianchi',
    starts_on: '2026-08-01',
  }
}

describe('cadastro de atividade recorrente', () => {
  it('aceita uma semanal bem formada', () => {
    expect(validateRecurringDraft(draft())).toEqual([])
  })

  it('exige o dia da semana na semanal e o dia do mês na mensal', () => {
    expect(validateRecurringDraft({ ...draft(), weekday: null }))
      .toContain('Escolha o dia da semana.')
    expect(validateRecurringDraft({ ...draft(), frequency: 'monthly', day_of_month: null }))
      .toContain('Escolha o dia do mês.')
  })

  it('recusa data final anterior à inicial', () => {
    expect(validateRecurringDraft({ ...draft(), ends_on: '2026-07-01' }))
      .toContain('A data final é anterior à inicial.')
  })

  it('o campo que não pertence à frequência vai NULO', () => {
    // Mandar os dois deixaria o cadastro ambíguo e o CHECK do banco recusaria
    // com uma mensagem que o operador não entende.
    const semanal = buildRecurringPayload({ ...draft(), weekday: 3, day_of_month: 15 })
    expect(semanal.weekday).toBe(3)
    expect(semanal.day_of_month).toBeNull()

    const mensal = buildRecurringPayload({
      ...draft(), frequency: 'monthly', weekday: 3, day_of_month: 15,
    })
    expect(mensal.day_of_month).toBe(15)
    expect(mensal.weekday).toBeNull()
  })

  it('contrato vazio vira null — é o "não consome" da suposição S4', () => {
    expect(buildRecurringPayload(draft()).contract_id).toBeNull()
    expect(buildRecurringPayload({ ...draft(), contract_id: 'abc' }).contract_id).toBe('abc')
  })

  it('avisa sobre fevereiro quando o dia escolhido é 29, 30 ou 31', () => {
    expect(shortMonthWarning({ ...draft(), frequency: 'monthly', day_of_month: 31 }))
      .toContain('último dia do mês')
    expect(shortMonthWarning({ ...draft(), frequency: 'monthly', day_of_month: 15 })).toBeNull()
    expect(shortMonthWarning({ ...draft(), frequency: 'weekly' })).toBeNull()
  })

  it('o rascunho de edição nasce do que está gravado', () => {
    const task: RecurringTask = {
      id: 'x', title: 'Patches', body: '', frequency: 'monthly', weekday: null,
      day_of_month: 5, at_time: '09:00', starts_on: '2026-01-01', ends_on: null,
      znuny_queue_name: 'Preventivos', service: null, type: null, priority: null,
      customer_user_login: 'ana', contract_id: null, active: true,
      schedule_label: 'todo dia 5, 09:00', next_occurrence: '2026-09-05', last_ticket_id: null,
    }
    const d = draftFromTask(task)
    expect(d.frequency).toBe('monthly')
    expect(d.day_of_month).toBe(5)
    expect(d.ends_on).toBe('')
  })
})

describe('agenda agrupada por data', () => {
  const e = (date: string, title: string): AgendaEntry =>
    ({ task_id: title, title, date, schedule_label: '', znuny_ticket_id: null })

  it('agrupa e ordena — é como o técnico lê a semana', () => {
    const groups = groupAgendaByDate([
      e('2026-09-07', 'Patches'),
      e('2026-08-31', 'Backup'),
      e('2026-08-31', 'Antivírus'),
    ])
    expect(groups.map(g => g.date)).toEqual(['2026-08-31', '2026-09-07'])
    expect(groups[0]!.items).toHaveLength(2)
  })

  it('agenda vazia não quebra', () => {
    expect(groupAgendaByDate([])).toEqual([])
  })
})

// ── importação ──────────────────────────────────────────────────────────────

function report(over: Partial<ImportReport> = {}): ImportReport {
  return {
    kind: 'tenants', dry_run: true, total: 3, valid: 3, invalid: 0,
    created: 0, skipped: 0, failed: 0, rows: [], ...over,
  }
}

describe('fluxo da importação', () => {
  it('só oferece importar DEPOIS de simular, e só se houver linha boa', () => {
    expect(canRun(null)).toBe(false)
    expect(canRun(report({ valid: 0, invalid: 3 }))).toBe(false)
    expect(canRun(report())).toBe(true)
  })

  it('o botão some depois de importar — senão alguém importa duas vezes', () => {
    expect(canRun(report({ dry_run: false, created: 3 }))).toBe(false)
  })

  it('a confirmação diz o NÚMERO, não "confirma?"', () => {
    expect(confirmationLabel(report({ valid: 47 }), 'tenants')).toBe('Importar 47 clientes?')
    expect(confirmationLabel(report({ valid: 1 }), 'tenant_users')).toBe('Importar 1 usuário?')
  })

  it('o resumo muda conforme for simulação ou execução', () => {
    expect(summarize(report())).toContain('pronta')
    expect(summarize(report({ dry_run: false, created: 2, skipped: 1 }))).toContain('criada')
  })
})

describe('safeCell (CSV injection)', () => {
  it('neutraliza o gatilho de fórmula do Excel', () => {
    expect(safeCell('=cmd|calc')).toBe("'=cmd|calc")
    expect(safeCell('+1+1')).toBe("'+1+1")
    expect(safeCell('-2')).toBe("'-2")
    expect(safeCell('@SUM(A1)')).toBe("'@SUM(A1)")
  })

  it('texto normal passa intacto', () => {
    expect(safeCell('Acme Indústria')).toBe('Acme Indústria')
    expect(safeCell('ana@acme.com')).toBe('ana@acme.com')
    expect(safeCell('')).toBe('')
  })
})
