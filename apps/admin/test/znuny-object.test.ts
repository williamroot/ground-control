// Spec #4 — lógica pura das telas de Znuny (filas, SLA): rascunho, validação
// (espelho leve do 422 do sidecar), montagem de payload e o formatador de
// minutos→legível. Sem Nuxt/DOM.
import { describe, expect, it } from 'vitest'
import {
  buildInvalidateQueuePayload,
  buildInvalidateSlaPayload,
  buildQueuePayload,
  buildSlaPayload,
  emptyQueueDraft,
  emptySlaDraft,
  extractItemId,
  extractItems,
  extractSupport,
  formatMinutes,
  isQueueDraftValid,
  isSlaDraftValid,
  queueDraftFromItem,
  slaDraftFromItem,
  toOptions,
  validateQueueDraft,
  validateSlaDraft,
  validBadgeColor,
  validLabelPt,
} from '../composables/useZnunyObject'

describe('formatMinutes', () => {
  it('formata minutos com o equivalente em horas', () => {
    expect(formatMinutes(240)).toBe('240 min · 4 h')
    expect(formatMinutes('240')).toBe('240 min · 4 h')
  })

  it('mostra hora fracionada quando não é múltiplo de 60', () => {
    expect(formatMinutes(90)).toBe('90 min · 1.5 h')
  })

  it('sinaliza 0 como desativado em vez de "0 h"', () => {
    expect(formatMinutes(0)).toBe('desativado (0 min)')
    expect(formatMinutes('0')).toBe('desativado (0 min)')
  })

  it('retorna travessão para vazio/nulo/inválido', () => {
    expect(formatMinutes(null)).toBe('—')
    expect(formatMinutes(undefined)).toBe('—')
    expect(formatMinutes('')).toBe('—')
    expect(formatMinutes('abc')).toBe('—')
  })
})

describe('toOptions', () => {
  it('normaliza dicionário id→nome', () => {
    expect(toOptions({ 1: 'Raw', 2: 'Postmaster' })).toEqual([
      { id: '1', name: 'Raw' },
      { id: '2', name: 'Postmaster' },
    ])
  })

  it('normaliza lista [{id, name}]', () => {
    expect(toOptions([{ id: 1, name: 'Raw' }, { id: 2, name: 'Postmaster' }])).toEqual([
      { id: '1', name: 'Raw' },
      { id: '2', name: 'Postmaster' },
    ])
  })

  it('normaliza lista com chaves PascalCase (ID/Name)', () => {
    expect(toOptions([{ ID: 3, Name: 'Fechado' }])).toEqual([{ id: '3', name: 'Fechado' }])
  })

  it('vazio/nulo vira lista vazia', () => {
    expect(toOptions(null)).toEqual([])
    expect(toOptions(undefined)).toEqual([])
  })
})

describe('extractItems / extractSupport', () => {
  it('extrai items de uma lista solta', () => {
    expect(extractItems([{ Name: 'a' }], 'Queue')).toEqual([{ Name: 'a' }])
  })

  it('extrai items de um envelope { items }', () => {
    expect(extractItems({ items: [{ Name: 'a' }] }, 'Queue')).toEqual([{ Name: 'a' }])
  })

  it('extrai items de um envelope { Queue }', () => {
    expect(extractItems({ Queue: [{ Name: 'a' }] }, 'Queue')).toEqual([{ Name: 'a' }])
  })

  it('sem items reconhecíveis vira lista vazia', () => {
    expect(extractItems({ foo: 'bar' }, 'Queue')).toEqual([])
    expect(extractItems(null, 'Queue')).toEqual([])
  })

  it('extrai o support de um envelope { support }', () => {
    expect(extractSupport({ items: [], support: { GroupList: { 1: 'Users' } } }))
      .toEqual({ GroupList: { 1: 'Users' } })
  })

  it('sem envelope support, usa o objeto todo (listas soltas ao lado dos items)', () => {
    expect(extractSupport({ GroupList: { 1: 'Users' } })).toEqual({ GroupList: { 1: 'Users' } })
  })
})

describe('extractItemId', () => {
  it('resolve pela chave PK conhecida por objeto', () => {
    expect(extractItemId({ QueueID: 7, Name: 'Suporte' })).toBe('7')
    expect(extractItemId({ SLAID: 9 })).toBe('9')
  })

  it('cai em ID/id genérico quando não há PK conhecida', () => {
    expect(extractItemId({ ID: 3 })).toBe('3')
    expect(extractItemId({ id: 4 })).toBe('4')
  })

  it('sem nenhuma chave reconhecível retorna vazio', () => {
    expect(extractItemId({ Name: 'x' })).toBe('')
  })
})

describe('validLabelPt / validBadgeColor', () => {
  it('traduz os nomes conhecidos do ValidList', () => {
    expect(validLabelPt('valid')).toBe('Válido')
    expect(validLabelPt('invalid')).toBe('Inválido')
    expect(validLabelPt('invalid-temporarily')).toBe('Inválido temporariamente')
  })

  it('nome desconhecido cai no valor original', () => {
    expect(validLabelPt('custom-status')).toBe('custom-status')
  })

  it('mapeia id de validade pra cor semântica', () => {
    expect(validBadgeColor('1')).toBe('success')
    expect(validBadgeColor('2')).toBe('error')
    expect(validBadgeColor('3')).toBe('warning')
    expect(validBadgeColor('9')).toBe('neutral')
  })
})

describe('Fila (Queue) — draft/validação/payload', () => {
  it('emptyQueueDraft começa válida como "valid" (ValidID=1)', () => {
    expect(emptyQueueDraft().ValidID).toBe('1')
  })

  it('reconstroi o draft a partir de um item do sidecar', () => {
    const draft = queueDraftFromItem({
      Name: 'Suporte N1', GroupID: 2, Comment: 'fila padrão', ValidID: 1,
      FirstResponseTime: 30, UpdateTime: 60, SolutionTime: 240, Calendar: '1',
      FollowUpID: 1, UnlockTimeout: 15,
    })
    expect(draft.Name).toBe('Suporte N1')
    expect(draft.GroupID).toBe('2')
    expect(draft.SolutionTime).toBe('240')
  })

  it('rejeita nome vazio ou fora de 2–200 caracteres', () => {
    const draft = { ...emptyQueueDraft(), GroupID: '1' }
    expect(isQueueDraftValid(draft)).toBe(false)
    expect(validateQueueDraft({ ...draft, Name: 'a' }).some(e => e.includes('Nome'))).toBe(true)
  })

  it('exige grupo selecionado', () => {
    const draft = { ...emptyQueueDraft(), Name: 'Suporte N1' }
    expect(validateQueueDraft(draft).some(e => e.includes('grupo'))).toBe(true)
  })

  it('rejeita tempo de minutos negativo ou fracionário', () => {
    const draft = { ...emptyQueueDraft(), Name: 'Suporte N1', GroupID: '1', FirstResponseTime: '-5' }
    expect(validateQueueDraft(draft).some(e => e.includes('1ª resposta'))).toBe(true)
    const draft2 = { ...emptyQueueDraft(), Name: 'Suporte N1', GroupID: '1', UpdateTime: '1.5' }
    expect(validateQueueDraft(draft2).some(e => e.includes('atualização'))).toBe(true)
  })

  it('tempos vazios são válidos (opcionais)', () => {
    const draft = { ...emptyQueueDraft(), Name: 'Suporte N1', GroupID: '1' }
    expect(isQueueDraftValid(draft)).toBe(true)
  })

  it('aceita um rascunho completo válido', () => {
    const draft = {
      ...emptyQueueDraft(),
      Name: 'Suporte N1',
      GroupID: '1',
      Comment: 'fila padrão',
      ValidID: '1',
      FirstResponseTime: '30',
      UpdateTime: '60',
      SolutionTime: '240',
      Calendar: '1',
      FollowUpID: '1',
      UnlockTimeout: '15',
    }
    expect(isQueueDraftValid(draft)).toBe(true)
  })

  it('buildQueuePayload converte minutos pra número e omite opcionais vazios', () => {
    const draft = { ...emptyQueueDraft(), Name: '  Suporte N1  ', GroupID: '1', FirstResponseTime: '30' }
    const payload = buildQueuePayload(draft)
    expect(payload.Name).toBe('Suporte N1')
    expect(payload.GroupID).toBe(1)
    expect(payload.FirstResponseTime).toBe(30)
    expect(payload.UpdateTime).toBeUndefined()
    expect(payload.Comment).toBeUndefined()
  })

  it('buildInvalidateQueuePayload força ValidID=2 mantendo os demais campos', () => {
    const draft = { ...emptyQueueDraft(), Name: 'Suporte N1', GroupID: '1', ValidID: '1' }
    const payload = buildInvalidateQueuePayload(draft)
    expect(payload.ValidID).toBe(2)
    expect(payload.Name).toBe('Suporte N1')
  })
})

describe('SLA — draft/validação/payload', () => {
  it('reconstroi ServiceIDs como array de strings', () => {
    const draft = slaDraftFromItem({ Name: 'SLA Padrão', ValidID: 1, ServiceIDs: [1, 2] })
    expect(draft.ServiceIDs).toEqual(['1', '2'])
  })

  it('rejeita percentual de notificação fora de 0–100', () => {
    const draft = { ...emptySlaDraft(), Name: 'SLA Padrão', FirstResponseNotify: '150' }
    expect(validateSlaDraft(draft).some(e => e.includes('Notificação de 1ª resposta'))).toBe(true)
    const draft2 = { ...emptySlaDraft(), Name: 'SLA Padrão', UpdateNotify: '-1' }
    expect(validateSlaDraft(draft2).some(e => e.includes('Notificação de atualização'))).toBe(true)
  })

  it('aceita um rascunho completo válido', () => {
    const draft = {
      ...emptySlaDraft(),
      Name: 'SLA Padrão',
      Comment: 'padrão pra todo mundo',
      ValidID: '1',
      Calendar: '1',
      FirstResponseTime: '30',
      FirstResponseNotify: '80',
      UpdateTime: '60',
      UpdateNotify: '80',
      SolutionTime: '240',
      SolutionNotify: '90',
      ServiceIDs: ['1', '2'],
    }
    expect(isSlaDraftValid(draft)).toBe(true)
  })

  it('buildSlaPayload converte ServiceIDs pra números', () => {
    const draft = { ...emptySlaDraft(), Name: 'SLA Padrão', ServiceIDs: ['1', '2'] }
    const payload = buildSlaPayload(draft)
    expect(payload.ServiceIDs).toEqual([1, 2])
  })

  it('buildInvalidateSlaPayload força ValidID=2', () => {
    const draft = { ...emptySlaDraft(), Name: 'SLA Padrão', ValidID: '1' }
    expect(buildInvalidateSlaPayload(draft).ValidID).toBe(2)
  })
})
