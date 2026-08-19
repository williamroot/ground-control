// R13b — regras dos checklists na interface.
import { describe, expect, it } from 'vitest'
import {
  availableTemplates,
  localPercent,
  parseItems,
  validateTemplate,
} from '../composables/useChecklists'

const item = (id: string, done: boolean) => ({
  id, text: id, done, done_by: null, done_at: null,
})

describe('progresso', () => {
  it('2 de 5 marcados = 40%', () => {
    expect(localPercent([
      item('a', true), item('b', true), item('c', false), item('d', false), item('e', false),
    ])).toBe(40)
  })

  it('lista vazia não vira 100% nem estoura', () => {
    expect(localPercent([])).toBe(0)
  })

  it('tudo marcado é 100%', () => {
    expect(localPercent([item('a', true), item('b', true)])).toBe(100)
  })
})

describe('itens do modelo', () => {
  it('uma linha, um item, na ordem escrita', () => {
    expect(parseItems('Backup\nDesligar\nTrocar')).toEqual(['Backup', 'Desligar', 'Trocar'])
  })

  it('linhas em branco somem', () => {
    expect(parseItems('Backup\n\n  \nTestar')).toEqual(['Backup', 'Testar'])
  })

  it('aceita o traço que a pessoa digita por hábito', () => {
    expect(parseItems('- Backup\n* Desligar\n• Trocar')).toEqual(['Backup', 'Desligar', 'Trocar'])
  })
})

describe('cadastro do modelo', () => {
  it('modelo sem item é recusado', () => {
    // Um modelo vazio só seria descoberto depois de aplicado a um chamado.
    expect(validateTemplate('Onboarding', '   \n\n')).toContain(
      'Escreva pelo menos um item — um por linha.',
    )
  })

  it('modelo sem nome é recusado', () => {
    expect(validateTemplate('  ', 'Backup')).toContain('Dê um nome ao modelo.')
  })

  it('modelo completo passa', () => {
    expect(validateTemplate('Onboarding', 'Criar usuário\nInstalar antivírus')).toEqual([])
  })
})

describe('seletor de modelos', () => {
  const tpl = (name: string, active = true) => ({
    id: name, name, description: null, active, items: ['a'],
  })

  it('não oferece o que já foi aplicado — aplicar de novo não faria nada', () => {
    const disponivel = availableTemplates(
      [tpl('Onboarding'), tpl('Troca de servidor')],
      [{
        id: '1', template_name: 'Onboarding', applied_by: 'x', applied_at: '',
        total: 1, done: 0, percent: 0, items: [],
      }],
    )
    expect(disponivel.map(t => t.name)).toEqual(['Troca de servidor'])
  })

  it('não oferece modelo desativado', () => {
    expect(availableTemplates([tpl('Antigo', false)], [])).toEqual([])
  })
})
