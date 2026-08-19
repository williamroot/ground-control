// R7 — regras da fila de aprovação no portal. Lógica pura.
import { describe, expect, it } from 'vitest'
import {
  canDecide,
  decisionError,
  statusColor,
  statusLabel,
  validateDecision,
} from '../composables/useApprovals'

describe('quem pode decidir', () => {
  it('aprovador e admin decidem; help-desk não', () => {
    expect(canDecide('approver')).toBe(true)
    // Em empresa pequena o aprovador é o próprio admin do portal.
    expect(canDecide('admin')).toBe(true)
    expect(canDecide('helpdesk')).toBe(false)
    expect(canDecide(null)).toBe(false)
    expect(canDecide(undefined)).toBe(false)
  })
})

describe('motivo da reprovação', () => {
  it('reprovar sem motivo é recusado', () => {
    // Sem o texto, o autor fica sem saber o que fazer a seguir.
    expect(validateDecision('rejected', '')).toHaveLength(1)
    expect(validateDecision('rejected', '   ')).toHaveLength(1)
  })

  it('reprovar com motivo passa', () => {
    expect(validateDecision('rejected', 'fora do escopo do contrato')).toEqual([])
  })

  it('aprovar não exige motivo', () => {
    expect(validateDecision('approved', '')).toEqual([])
  })
})

describe('mensagens de erro', () => {
  it('explica o 409 sem parecer falha', () => {
    // Dois aprovadores clicando quase juntos: o segundo precisa entender que
    // a decisão do primeiro valeu.
    expect(decisionError(409)).toContain('já foi decidido')
  })

  it('explica 403 e 404', () => {
    expect(decisionError(403)).toContain('permissão')
    expect(decisionError(404)).toContain('não encontrado')
  })

  it('cai no detalhe do servidor quando não conhece o código', () => {
    expect(decisionError(500, 'boom')).toBe('boom')
    expect(decisionError(undefined)).toContain('Não foi possível')
  })
})

describe('rótulos', () => {
  it('traduz os estados', () => {
    expect(statusLabel('pending')).toBe('Aguardando decisão')
    expect(statusLabel('approved')).toBe('Aprovado')
    expect(statusLabel('rejected')).toBe('Reprovado')
    expect(statusLabel('outro')).toBe('outro')
  })

  it('dá cor a cada estado', () => {
    expect(statusColor('pending')).toBe('warning')
    expect(statusColor('approved')).toBe('success')
    expect(statusColor('rejected')).toBe('error')
    expect(statusColor('x')).toBe('neutral')
  })
})
