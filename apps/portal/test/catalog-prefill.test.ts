import { describe, expect, it } from 'vitest'
import {
  matchMetaKey,
  prefillFromCatalogItem,
  resolveServicoId,
} from '../components/ticket/catalog-prefill'

// Spec #3 · V2 — pré-preenchimento de /tickets/novo a partir de
// ?servico=<id> do catálogo. Ver comentário no módulo para a divergência
// documentada do campo "fila" (backend não aceita/expõe queue hoje).

describe('resolveServicoId: leitura da query ?servico', () => {
  it('string → o próprio id', () => {
    expect(resolveServicoId('abc-123')).toBe('abc-123')
  })
  it('array (query repetida) → primeiro elemento', () => {
    expect(resolveServicoId(['abc', 'def'])).toBe('abc')
  })
  it('ausente → string vazia', () => {
    expect(resolveServicoId(undefined)).toBe('')
  })
})

describe('matchMetaKey: acha a Key do meta por Key OU Value (case-insensitive)', () => {
  const services = [
    { Key: 'svc-access', Value: 'Acesso e Senhas' },
    { Key: 'svc-infra', Value: 'Infraestrutura' },
  ]
  it('bate por Key', () => {
    expect(matchMetaKey(services, 'svc-infra')).toBe('svc-infra')
  })
  it('bate por Value (case-insensitive)', () => {
    expect(matchMetaKey(services, 'acesso e senhas')).toBe('svc-access')
  })
  it('sem valor desejado → undefined', () => {
    expect(matchMetaKey(services, null)).toBeUndefined()
    expect(matchMetaKey(services, undefined)).toBeUndefined()
    expect(matchMetaKey(services, '')).toBeUndefined()
  })
  it('nenhuma opção corresponde → undefined (nunca quebra)', () => {
    expect(matchMetaKey(services, 'svc-desconhecido')).toBeUndefined()
  })
})

describe('prefillFromCatalogItem: valores iniciais do form (todos editáveis depois)', () => {
  const services = [{ Key: 'svc-access', Value: 'Acesso e Senhas' }]
  const priorities = [{ Key: '3 normal', Value: 'Normal' }]

  it('item null (id ausente/inexistente/inativo) → nada pré-preenchido', () => {
    expect(prefillFromCatalogItem(null, services, priorities)).toEqual({
      title: '',
      service: undefined,
      priority: undefined,
    })
  })

  it('item resolvido preenche title/service/priority a partir do meta', () => {
    const item = { name: 'Reset de senha', znuny_service: 'svc-access', default_priority: '3 normal' }
    expect(prefillFromCatalogItem(item, services, priorities)).toEqual({
      title: 'Reset de senha',
      service: 'svc-access',
      priority: '3 normal',
    })
  })

  it('service/priority do item sem correspondência no meta → undefined (sem quebrar)', () => {
    const item = { name: 'Provisionar servidor', znuny_service: 'inexistente', default_priority: null }
    expect(prefillFromCatalogItem(item, services, priorities)).toEqual({
      title: 'Provisionar servidor',
      service: undefined,
      priority: undefined,
    })
  })
})
