// V-R5.5 — seleção de filas por cliente (T-R5.4).
//
// A validação aqui espelha a do sidecar de propósito. A verdade continua sendo
// o 422 dele (que ainda confere cada id contra a lista viva do Znuny), mas o
// operador não precisa de um round-trip para descobrir que esqueceu de marcar
// a fila padrão.
import { describe, expect, it } from 'vitest'
import {
  buildQueuesPayload,
  selectionFromTenantQueues,
  servedByLabel,
  setDefault,
  toggleQueue,
  validateQueueSelection,
  type TenantQueue,
} from '../composables/useTenantQueues'

describe('validateQueueSelection', () => {
  it('recusa seleção vazia', () => {
    expect(validateQueueSelection([])).toEqual(['Selecione ao menos uma fila.'])
  })

  it('recusa seleção sem padrão', () => {
    expect(validateQueueSelection([
      { id: 3, is_default: false },
      { id: 5, is_default: false },
    ])).toEqual(['Marque uma fila como padrão.'])
  })

  it('recusa duas padrões', () => {
    expect(validateQueueSelection([
      { id: 3, is_default: true },
      { id: 5, is_default: true },
    ])).toContain('Só uma fila pode ser a padrão.')
  })

  it('aceita uma padrão entre várias', () => {
    expect(validateQueueSelection([
      { id: 3, is_default: true },
      { id: 5, is_default: false },
    ])).toEqual([])
  })

  it('recusa fila repetida', () => {
    expect(validateQueueSelection([
      { id: 3, is_default: true },
      { id: 3, is_default: false },
    ])).toContain('Fila repetida na seleção.')
  })
})

describe('setDefault', () => {
  it('marcar uma padrão desmarca a anterior', () => {
    const out = setDefault([
      { id: 3, is_default: true },
      { id: 5, is_default: false },
    ], 5)
    expect(out).toEqual([
      { id: 3, is_default: false },
      { id: 5, is_default: true },
    ])
  })
})

describe('toggleQueue', () => {
  it('adiciona a fila ausente, sem padrão', () => {
    expect(toggleQueue([], 7)).toEqual([{ id: 7, is_default: false }])
  })

  it('remove a fila presente', () => {
    expect(toggleQueue([{ id: 7, is_default: false }], 7)).toEqual([])
  })

  it('remover a fila padrão deixa a seleção sem padrão — e a validação pega', () => {
    const out = toggleQueue([
      { id: 3, is_default: true },
      { id: 5, is_default: false },
    ], 3)
    expect(out).toEqual([{ id: 5, is_default: false }])
    expect(validateQueueSelection(out)).toEqual(['Marque uma fila como padrão.'])
  })
})

describe('buildQueuesPayload', () => {
  it('ordena por id e remove duplicata', () => {
    const payload = buildQueuesPayload([
      { id: 9, is_default: false },
      { id: 3, is_default: true },
      { id: 9, is_default: false },
    ])
    expect(payload.queues).toEqual([
      { queue_id: 3, is_default: true },
      { queue_id: 9, is_default: false },
    ])
  })

  it('seleção vazia gera lista vazia — é como se limpa a configuração', () => {
    expect(buildQueuesPayload([])).toEqual({ queues: [] })
  })
})

describe('selectionFromTenantQueues', () => {
  it('converte a resposta do sidecar em seleção editável', () => {
    const rows: TenantQueue[] = [
      { queue_id: 3, queue_name: 'Suporte::N1', is_default: true, group_id: 2, group_name: 'suporte' },
      { queue_id: 5, queue_name: 'IMAC', is_default: false, group_id: 2, group_name: 'suporte' },
    ]
    expect(selectionFromTenantQueues(rows)).toEqual([
      { id: 3, is_default: true },
      { id: 5, is_default: false },
    ])
  })
})

describe('servedByLabel (aceite A5.5)', () => {
  it('mostra grupo e contagem', () => {
    expect(servedByLabel('suporte', 3)).toBe('suporte (3 agentes)')
    expect(servedByLabel('suporte', 1)).toBe('suporte (1 agente)')
  })

  it('sem contagem, mostra só o grupo — nunca "0 agentes" inventado', () => {
    expect(servedByLabel('suporte', null)).toBe('suporte')
    expect(servedByLabel('suporte', undefined)).toBe('suporte')
  })

  it('fila sem grupo mostra travessão', () => {
    expect(servedByLabel(null, 4)).toBe('—')
  })
})
