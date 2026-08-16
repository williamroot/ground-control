// V-R18b.6 / V-R18a.5 — helpers das telas de relatório e consumo (Onda 3).
//
// Dois riscos concretos cobertos aqui:
//   1. mês inválido chegando a virar chamada de API (o backend recusa, mas o
//      operador não deveria precisar do round-trip para saber);
//   2. horas e reais no mesmo gráfico — que é requisito do vídeo (11:00), não
//      detalhe estético: somar as duas coisas não é arredondar, é errar.
import { describe, expect, it } from 'vitest'
import {
  bucketLabel,
  formatValue,
  groupSeriesByKind,
  isValidMonth,
  monthLabelPt,
  monthRange,
  previousMonth,
  unitLabel,
  type ContractSeries,
} from '../composables/useReports'
import { isReportMonth } from '../server/utils/reports'

describe('monthRange', () => {
  it('devolve o primeiro e o último dia do mês', () => {
    expect(monthRange('2026-05')).toEqual(['2026-05-01', '2026-05-31'])
    expect(monthRange('2026-02')).toEqual(['2026-02-01', '2026-02-28'])
    expect(monthRange('2024-02')).toEqual(['2024-02-01', '2024-02-29']) // bissexto
    expect(monthRange('2026-04')).toEqual(['2026-04-01', '2026-04-30'])
  })

  it('recusa mês inválido — e é assim que a tela não chama a API', () => {
    expect(monthRange('2026-13')).toBeNull()
    expect(monthRange('2026-00')).toBeNull()
    expect(monthRange('202605')).toBeNull()
    expect(monthRange('2026-5')).toBeNull()
    expect(monthRange('')).toBeNull()
    expect(monthRange('maio')).toBeNull()
    expect(monthRange('1999-05')).toBeNull()
  })

  it('isValidMonth acompanha o monthRange', () => {
    expect(isValidMonth('2026-05')).toBe(true)
    expect(isValidMonth('2026-13')).toBe(false)
  })
})

describe('guard do proxy (server/utils)', () => {
  it('recusa o mesmo conjunto que a tela recusa', () => {
    expect(isReportMonth('2026-05')).toBe(true)
    for (const bad of ['2026-13', '2026-00', '202605', '', 'maio', null, undefined, 5]) {
      expect(isReportMonth(bad)).toBe(false)
    }
  })
})

describe('previousMonth', () => {
  it('volta um mês, virando o ano quando precisa', () => {
    expect(previousMonth(new Date(Date.UTC(2026, 7, 16)))).toBe('2026-07')
    expect(previousMonth(new Date(Date.UTC(2026, 0, 5)))).toBe('2025-12')
  })
})

describe('monthLabelPt', () => {
  it('escreve o mês por extenso', () => {
    expect(monthLabelPt('2026-05')).toBe('maio/2026')
    expect(monthLabelPt('2026-03')).toBe('março/2026')
  })
  it('mês inválido volta como veio, sem inventar', () => {
    expect(monthLabelPt('2026-13')).toBe('2026-13')
  })
})

describe('unitLabel (aceite A18a.2)', () => {
  it('cada tipo de contrato tem a sua unidade', () => {
    expect(unitLabel('hours')).toBe('h')
    expect(unitLabel('brl')).toBe('R$')
    expect(unitLabel('services')).toBe('atend.')
  })
  it('contrato sem saldo não tem unidade — nem gráfico', () => {
    expect(unitLabel('n/a')).toBe('')
  })
})

describe('formatValue', () => {
  it('horas saem em horas e reais saem em reais', () => {
    expect(formatValue('hours', 5)).toContain('h')
    expect(formatValue('hours', 5)).toContain('5,00')
    // `toLocaleString` usa espaço não-quebrável depois do R$ em algumas versões
    // do ICU; normalizamos para o teste não depender disso.
    expect(formatValue('brl', 1234.56).replace(/\u00a0/g, ' ')).toBe('R$ 1.234,56')
    expect(formatValue('services', 3)).toBe('3 atend.')
    expect(formatValue('n/a', 0)).toBe('—')
  })
})

describe('groupSeriesByKind (aceite A18a.2/A18a.4)', () => {
  const s = (code: string, kind: ContractSeries['kind']): ContractSeries => ({
    contract_id: code,
    code,
    type: 'x',
    kind,
    points: [{ bucket: '2026-06-01', value: 1 }],
  })

  it('horas e reais viram DOIS grupos — nunca o mesmo gráfico', () => {
    const groups = groupSeriesByKind([s('A', 'hours'), s('B', 'brl'), s('C', 'hours')])
    expect(groups).toHaveLength(2)
    const hours = groups.find(g => g.kind === 'hours')!
    expect(hours.series.map(x => x.code)).toEqual(['A', 'C'])
    expect(groups.find(g => g.kind === 'brl')!.series.map(x => x.code)).toEqual(['B'])
  })

  it('contrato sem saldo some — gráfico vazio engana (A18a.4)', () => {
    expect(groupSeriesByKind([s('A', 'n/a')])).toEqual([])
    const groups = groupSeriesByKind([s('A', 'n/a'), s('B', 'hours')])
    expect(groups).toHaveLength(1)
    expect(groups[0]!.kind).toBe('hours')
  })

  it('lista vazia não quebra', () => {
    expect(groupSeriesByKind([])).toEqual([])
  })
})

describe('bucketLabel', () => {
  it('encurta a data do balde', () => {
    expect(bucketLabel('2026-06-01')).toBe('jun/26')
    expect(bucketLabel('2026-12-01')).toBe('dez/26')
  })
  it('formato inesperado volta como veio, sem inventar rótulo', () => {
    expect(bucketLabel('2026-06')).toBe('2026-06')
    expect(bucketLabel('qualquer')).toBe('qualquer')
    expect(bucketLabel('2026-13-01')).toBe('2026-13-01')
  })
})
