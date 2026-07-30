// Spec #4 (Bloco B) — lógica pura do editor de definição de classes de CI.
// Sem Nuxt/DOM: dirty-check, guarda de salvamento e extração da mensagem do
// `DefinitionCheck` (422) que o sidecar repassa.
import { describe, expect, it } from 'vitest'
import {
  buildDefinitionPayload,
  ciValidColor,
  ciValidLabel,
  extractDefinitionError,
  isDefinitionDirty,
  isDefinitionSaveable,
} from '../composables/useCiDefinition'

describe('ciValidLabel/ciValidColor', () => {
  it('traduz os três estados de validade do Znuny', () => {
    expect(ciValidLabel('1')).toBe('válido')
    expect(ciValidLabel(2)).toBe('inválido')
    expect(ciValidLabel('3')).toBe('inválido temporariamente')
    expect(ciValidLabel(undefined)).toBe('desconhecido')
  })

  it('cor semântica acompanha o estado (H8, sem cor de marca)', () => {
    expect(ciValidColor('1')).toBe('success')
    expect(ciValidColor('2')).toBe('error')
    expect(ciValidColor('3')).toBe('warning')
    expect(ciValidColor('99')).toBe('neutral')
  })
})

describe('isDefinitionDirty', () => {
  it('sem mudança não está suja', () => {
    expect(isDefinitionDirty('a: 1\n', 'a: 1\n')).toBe(false)
  })

  it('mudança de conteúdo está suja', () => {
    expect(isDefinitionDirty('a: 1\n', 'a: 2\n')).toBe(true)
  })

  it('ignora espaços nas pontas (não é mudança real)', () => {
    expect(isDefinitionDirty('a: 1', '  a: 1  ')).toBe(false)
  })
})

describe('isDefinitionSaveable', () => {
  it('rejeita rascunho vazio', () => {
    expect(isDefinitionSaveable('')).toBe(false)
    expect(isDefinitionSaveable('   \n  ')).toBe(false)
  })

  it('aceita rascunho com conteúdo', () => {
    expect(isDefinitionSaveable('---\nName: teste\n')).toBe(true)
  })
})

describe('buildDefinitionPayload', () => {
  it('monta o corpo do PUT com a definição crua', () => {
    expect(buildDefinitionPayload('---\nx: 1\n')).toEqual({ Definition: '---\nx: 1\n' })
  })
})

describe('extractDefinitionError — a mensagem do DefinitionCheck precisa aparecer', () => {
  it('usa a mensagem do sidecar quando presente', () => {
    const err = { statusCode: 422, data: { detail: 'Attribute "Name" is required in row 3' } }
    expect(extractDefinitionError(err)).toBe('Attribute "Name" is required in row 3')
  })

  it('422 sem detalhe cai num texto genérico, mas ainda assim explica que foi recusa do Znuny', () => {
    const err = { statusCode: 422, data: {} }
    expect(extractDefinitionError(err)).toContain('Znuny recusou')
  })

  it('erro sem statusCode/detail cai no genérico de falha ao salvar', () => {
    expect(extractDefinitionError(new Error('boom'))).toContain('Falha ao salvar')
  })
})
