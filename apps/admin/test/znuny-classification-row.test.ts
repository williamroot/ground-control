// Spec #4 — ClassificationRow.vue (HTML nativo, sem U*/@nuxt/icon). Reusada
// pelas três abas de Classificação; testa render, slot de coluna extra
// (usado só por Estados) e emissão de edit/invalidate.
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ClassificationRow from '../components/znuny/ClassificationRow.vue'

describe('ClassificationRow', () => {
  it('renderiza nome e rótulo de validade', () => {
    const wrapper = mount(ClassificationRow, {
      props: { name: 'Incidente', validId: '1', validLabel: 'válido' },
    })
    expect(wrapper.text()).toContain('Incidente')
    expect(wrapper.find('[data-testid="classification-status"]').text()).toBe('válido')
  })

  it('renderiza o slot de coluna extra (usado por Estados)', () => {
    const wrapper = mount(ClassificationRow, {
      props: { name: 'Fechado', validId: '1', validLabel: 'válido' },
      slots: { default: '<td data-testid="extra-col">new</td>' },
    })
    expect(wrapper.find('[data-testid="extra-col"]').text()).toBe('new')
  })

  it('mostra "Invalidar" apenas quando validId=1', () => {
    const valid = mount(ClassificationRow, { props: { name: 'x', validId: '1', validLabel: 'válido' } })
    expect(valid.find('[data-testid="classification-invalidate"]').exists()).toBe(true)

    const invalid = mount(ClassificationRow, { props: { name: 'x', validId: '2', validLabel: 'inválido' } })
    expect(invalid.find('[data-testid="classification-invalidate"]').exists()).toBe(false)
  })

  it('emite edit e invalidate ao clicar', async () => {
    const wrapper = mount(ClassificationRow, { props: { name: 'x', validId: '1', validLabel: 'válido' } })
    await wrapper.find('[data-testid="classification-edit"]').trigger('click')
    expect(wrapper.emitted('edit')).toBeTruthy()
    await wrapper.find('[data-testid="classification-invalidate"]').trigger('click')
    expect(wrapper.emitted('invalidate')).toBeTruthy()
  })
})
