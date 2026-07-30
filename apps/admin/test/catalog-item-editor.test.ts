// Spec #3 (V2) — lógica pura do formulário de Catálogo de Serviços do console.
// Sem Nuxt/DOM: testa allowlist de ícone, validação (espelho do 422 do
// sidecar) e montagem do payload de criação/edição.
import { describe, expect, it } from 'vitest'
import {
  buildCatalogItemPayload,
  CATALOG_ICONS,
  catalogDraftFromItem,
  catalogIconLucide,
  emptyCatalogDraft,
  isCatalogItemValid,
  validateCatalogItem,
  type CatalogItemRow,
} from '../composables/useCatalogItem'

describe('validateCatalogItem — espelho do 422', () => {
  it('rejeita rascunho vazio', () => {
    const draft = emptyCatalogDraft()
    draft.name = ''
    draft.category = ''
    expect(isCatalogItemValid(draft)).toBe(false)
  })

  it('nome fora de 3–120 é inválido', () => {
    const draft = { ...emptyCatalogDraft(), name: 'ab', category: 'redes' }
    expect(validateCatalogItem(draft).some(e => e.includes('Nome'))).toBe(true)
  })

  it('sla_hours fora de 1–720 é inválido', () => {
    const draft = { ...emptyCatalogDraft(), name: 'Reset de senha', category: 'contas', sla_hours: '0' }
    expect(validateCatalogItem(draft).some(e => e.includes('SLA'))).toBe(true)
    const draft2 = { ...emptyCatalogDraft(), name: 'Reset de senha', category: 'contas', sla_hours: '721' }
    expect(validateCatalogItem(draft2).some(e => e.includes('SLA'))).toBe(true)
  })

  it('sla_hours vazio é válido (opcional)', () => {
    const draft = { ...emptyCatalogDraft(), name: 'Reset de senha', category: 'contas', sla_hours: '' }
    expect(isCatalogItemValid(draft)).toBe(true)
  })

  it('ícone fora da allowlist é inválido', () => {
    const draft = { ...emptyCatalogDraft(), name: 'Reset de senha', category: 'contas', icon: 'rocket' }
    expect(validateCatalogItem(draft).some(e => e.includes('Ícone'))).toBe(true)
  })

  it('todos os ícones da allowlist são aceitos', () => {
    for (const icon of CATALOG_ICONS) {
      const draft = { ...emptyCatalogDraft(), name: 'Reset de senha', category: 'contas', icon }
      expect(isCatalogItemValid(draft)).toBe(true)
    }
  })

  it('sort_order fora de 0–999 é inválido', () => {
    const draft = { ...emptyCatalogDraft(), name: 'Reset de senha', category: 'contas', sort_order: 1000 }
    expect(validateCatalogItem(draft).some(e => e.includes('Ordem'))).toBe(true)
    const draft2 = { ...emptyCatalogDraft(), name: 'Reset de senha', category: 'contas', sort_order: -1 }
    expect(validateCatalogItem(draft2).some(e => e.includes('Ordem'))).toBe(true)
  })

  it('descrição acima de 1000 chars é inválida', () => {
    const draft = {
      ...emptyCatalogDraft(),
      name: 'Reset de senha',
      category: 'contas',
      description: 'x'.repeat(1001),
    }
    expect(validateCatalogItem(draft).some(e => e.includes('Descrição'))).toBe(true)
  })

  it('aceita um rascunho válido completo', () => {
    const draft = {
      ...emptyCatalogDraft(),
      name: 'Provisionar novo usuário',
      category: 'contas',
      description: 'Cria conta de rede e e-mail.',
      sla_hours: '24',
      icon: 'user-plus',
      znuny_queue: 'TI::Contas',
      znuny_service: 'Provisionamento',
      default_priority: '3 normal',
      active: true,
      sort_order: 5,
    }
    expect(isCatalogItemValid(draft)).toBe(true)
  })
})

describe('buildCatalogItemPayload', () => {
  it('converte sla_hours para número e omite campos opcionais vazios', () => {
    const draft = { ...emptyCatalogDraft(), name: '  Reset de senha  ', category: '  contas  ', sla_hours: '24' }
    const payload = buildCatalogItemPayload(draft)
    expect(payload.name).toBe('Reset de senha')
    expect(payload.category).toBe('contas')
    expect(payload.sla_hours).toBe(24)
    expect(payload.description).toBeUndefined()
    expect(payload.znuny_queue).toBeUndefined()
  })

  it('sla_hours vazio não entra no payload', () => {
    const draft = { ...emptyCatalogDraft(), name: 'Reset de senha', category: 'contas', sla_hours: '' }
    const payload = buildCatalogItemPayload(draft)
    expect(payload.sla_hours).toBeUndefined()
  })
})

describe('catalogDraftFromItem', () => {
  it('preenche o rascunho a partir do item carregado (nulos viram vazio)', () => {
    const item: CatalogItemRow = {
      id: '1',
      name: 'Reset de senha',
      category: 'contas',
      description: null,
      sla_hours: null,
      icon: 'lock',
      znuny_queue: null,
      znuny_service: null,
      default_priority: null,
      active: false,
      sort_order: 3,
    }
    const draft = catalogDraftFromItem(item)
    expect(draft.description).toBe('')
    expect(draft.sla_hours).toBe('')
    expect(draft.znuny_queue).toBe('')
    expect(draft.active).toBe(false)
    expect(draft.sort_order).toBe(3)
  })
})

describe('catalogIconLucide', () => {
  it('mapeia ícone salvo para o nome Lucide', () => {
    expect(catalogIconLucide('user-plus')).toBe('i-lucide-user-plus')
  })

  it('cai no ícone padrão quando desconhecido', () => {
    expect(catalogIconLucide('rocket')).toBe('i-lucide-ticket')
  })
})
