// Spec #4 (Bloco A) — lógica pura das três abas de Classificação (Tipos de
// chamado, Estados, Prioridades). Espelho leve do 422 do sidecar. "Excluir"
// não existe: ValidID=2 é a única forma de remoção ("Invalidar").
import { describe, expect, it } from 'vitest'
import {
  buildInvalidatePriorityPayload,
  buildInvalidateStatePayload,
  buildInvalidateTypePayload,
  buildPriorityPayload,
  buildStatePayload,
  buildTypePayload,
  emptyPriorityDraft,
  emptyStateDraft,
  emptyTypeDraft,
  priorityDraftFromItem,
  stateDraftFromItem,
  typeDraftFromItem,
  validateStateDraft,
  validateTypeDraft,
} from '../composables/useZnunyClassification'

describe('Tipo de chamado', () => {
  it('rejeita nome vazio', () => {
    expect(validateTypeDraft(emptyTypeDraft()).length).toBeGreaterThan(0)
  })

  it('aceita rascunho válido', () => {
    expect(validateTypeDraft({ name: 'Incidente', validId: '1' })).toEqual([])
  })

  it('typeDraftFromItem normaliza campos crus (número vira string, ValidID ausente cai em "1")', () => {
    expect(typeDraftFromItem({ Name: 'Incidente', ValidID: 1 })).toEqual({ name: 'Incidente', validId: '1' })
    expect(typeDraftFromItem({ Name: 'Incidente' })).toEqual({ name: 'Incidente', validId: '1' })
  })

  it('buildTypePayload converte ValidID para number', () => {
    expect(buildTypePayload({ name: 'Incidente', validId: '1' })).toEqual({ Name: 'Incidente', ValidID: 1 })
  })

  it('buildInvalidateTypePayload força ValidID=2', () => {
    expect(buildInvalidateTypePayload({ name: 'Incidente', validId: '1' })).toEqual({ Name: 'Incidente', ValidID: 2 })
  })
})

describe('Prioridade — mesma forma do Tipo', () => {
  it('aceita rascunho válido e monta payload', () => {
    const draft = { ...emptyPriorityDraft(), name: '3 normal' }
    expect(buildPriorityPayload(draft)).toEqual({ Name: '3 normal', ValidID: 1 })
  })

  it('priorityDraftFromItem preenche a partir do item cru', () => {
    expect(priorityDraftFromItem({ Name: '3 normal', ValidID: '1' })).toEqual({ name: '3 normal', validId: '1' })
  })

  it('buildInvalidatePriorityPayload força ValidID=2', () => {
    expect(buildInvalidatePriorityPayload({ name: '3 normal', validId: '1' }).ValidID).toBe(2)
  })
})

describe('Estado', () => {
  it('rejeita sem tipo de estado (TypeID obrigatório)', () => {
    const draft = { ...emptyStateDraft(), name: 'Fechado', typeId: '' }
    expect(validateStateDraft(draft).some(e => e.includes('Tipo de estado'))).toBe(true)
  })

  it('aceita rascunho válido', () => {
    const draft = { name: 'Fechado', comment: '', validId: '1', typeId: '4' }
    expect(validateStateDraft(draft)).toEqual([])
  })

  it('stateDraftFromItem normaliza campos crus — comentário ausente vira string vazia', () => {
    const draft = stateDraftFromItem({ Name: 'Fechado', Comment: null, ValidID: 1, TypeID: 4 })
    expect(draft).toEqual({ name: 'Fechado', comment: '', validId: '1', typeId: '4' })
  })

  it('buildStatePayload converte ValidID/TypeID para number, omite comentário vazio', () => {
    const payload = buildStatePayload({ name: 'Fechado', comment: '', validId: '1', typeId: '4' })
    expect(payload).toEqual({ Name: 'Fechado', Comment: undefined, ValidID: 1, TypeID: 4 })
  })

  it('buildStatePayload preserva comentário preenchido', () => {
    const payload = buildStatePayload({ name: 'Fechado', comment: '  ok  ', validId: '1', typeId: '4' })
    expect(payload.Comment).toBe('ok')
  })

  it('buildInvalidateStatePayload força ValidID=2, mantém TypeID', () => {
    const payload = buildInvalidateStatePayload({ name: 'Fechado', comment: '', validId: '1', typeId: '4' })
    expect(payload.ValidID).toBe(2)
    expect(payload.TypeID).toBe(4)
  })
})
