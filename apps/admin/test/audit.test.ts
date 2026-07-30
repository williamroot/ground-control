// Spec #3, V5 — rótulos, cores e paginação da trilha de auditoria.
import { describe, expect, it } from 'vitest'
import {
  actionColor,
  actionLabel,
  actorLabel,
  AUDIT_ACTIONS,
  clampAuditLimit,
  DEFAULT_AUDIT_LIMIT,
  entityLabel,
  MAX_AUDIT_LIMIT,
} from '../shared/audit'

describe('actionLabel/actionColor', () => {
  it('traduz as 5 ações congeladas', () => {
    expect(AUDIT_ACTIONS).toHaveLength(5)
    expect(actionLabel('create')).toBe('Criação')
    expect(actionLabel('delete')).toBe('Exclusão')
    expect(actionColor('delete')).toBe('error')
    expect(actionColor('create')).toBe('success')
  })

  it('ação desconhecida cai em neutro/verbatim', () => {
    expect(actionLabel('mystery')).toBe('mystery')
    expect(actionColor('mystery')).toBe('neutral')
  })

  it('nunca usa cor de marca (H8) — só tokens semânticos', () => {
    const allowed = new Set(['success', 'info', 'error', 'neutral', 'warning'])
    for (const a of AUDIT_ACTIONS) {
      expect(allowed.has(actionColor(a))).toBe(true)
    }
  })
})

describe('actorLabel', () => {
  it('prefere o login quando presente', () => {
    expect(actorLabel('agent', 'joao.silva')).toBe('joao.silva')
  })

  it('sem login, usa o tipo por extenso', () => {
    expect(actorLabel('system', null)).toBe('Sistema')
    expect(actorLabel('customer', '')).toBe('Cliente')
  })

  it('tipo desconhecido sem login cai em Desconhecido', () => {
    expect(actorLabel(null, null)).toBe('Desconhecido')
  })
})

describe('entityLabel', () => {
  it('combina entity e entity_id com separador', () => {
    expect(entityLabel('kb_article', 'abc-123')).toBe('kb_article · abc-123')
  })

  it('sem entity_id mostra só a entidade', () => {
    expect(entityLabel('tenant', null)).toBe('tenant')
  })
})

describe('clampAuditLimit', () => {
  it('mantém valores dentro do limite', () => {
    expect(clampAuditLimit(50)).toBe(50)
  })

  it('trava no máximo 200', () => {
    expect(clampAuditLimit(9999)).toBe(MAX_AUDIT_LIMIT)
  })

  it('valores inválidos caem no default', () => {
    expect(clampAuditLimit(0)).toBe(DEFAULT_AUDIT_LIMIT)
    expect(clampAuditLimit(-5)).toBe(DEFAULT_AUDIT_LIMIT)
    expect(clampAuditLimit(Number.NaN)).toBe(DEFAULT_AUDIT_LIMIT)
  })
})
