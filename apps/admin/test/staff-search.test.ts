// Spec #3, V6 — busca federada do staff: gatilho por tamanho mínimo e
// detecção de "tem resultado" para decidir quais seções mostrar.
import { describe, expect, it } from 'vitest'
import { hasAnyResult, MIN_QUERY_LENGTH, SEARCH_SECTIONS, shouldSearch, type StaffSearchResponse } from '../composables/useStaffSearch'

describe('shouldSearch', () => {
  it('exige ao menos 2 caracteres (após trim)', () => {
    expect(MIN_QUERY_LENGTH).toBe(2)
    expect(shouldSearch('a')).toBe(false)
    expect(shouldSearch('ab')).toBe(true)
    expect(shouldSearch('  a  ')).toBe(false)
    expect(shouldSearch('')).toBe(false)
  })
})

describe('hasAnyResult', () => {
  const empty: StaffSearchResponse = { tenants: [], tickets: [], kb: [] }

  it('resposta vazia -> false', () => {
    expect(hasAnyResult(empty)).toBe(false)
  })

  it('null/undefined -> false', () => {
    expect(hasAnyResult(null)).toBe(false)
    expect(hasAnyResult(undefined)).toBe(false)
  })

  it('qualquer seção com item -> true', () => {
    expect(hasAnyResult({ ...empty, kb: [{ id: '1', title: 'x', path: '/x' }] })).toBe(true)
  })
})

describe('SEARCH_SECTIONS', () => {
  it('cobre as 3 seções do contrato (tenants, tickets, kb)', () => {
    expect(SEARCH_SECTIONS.map(s => s.key)).toEqual(['tenants', 'tickets', 'kb'])
  })
})
