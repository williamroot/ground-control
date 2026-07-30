// Spec #4 — ServiceTreeRow.vue (HTML nativo, sem U*/@nuxt/icon, monta limpo
// no vitest — lição #1M..#1Q). Testa indentação por profundidade, exibição do
// nome-folha, e emissão de edit/invalidate.
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ServiceTreeRow from '../components/znuny/ServiceTreeRow.vue'
import type { ServiceRow } from '../composables/useServiceTree'

const ROW: ServiceRow = {
  id: '3',
  Name: 'Suporte::Rede::Wi-Fi',
  ParentID: '2',
  Comment: 'rede sem fio',
  ValidID: '1',
  TypeID: '',
  Criticality: '',
}

function mountRow(row: ServiceRow = ROW, depth = 2) {
  return mount(ServiceTreeRow, {
    props: { row, leafName: 'Wi-Fi', depth, validLabel: 'válido' },
    global: { stubs: {} },
  })
}

describe('ServiceTreeRow', () => {
  it('renderiza o nome-folha e o comentário', () => {
    const wrapper = mountRow()
    expect(wrapper.find('[data-testid="service-leaf-name"]').text()).toBe('Wi-Fi')
    expect(wrapper.text()).toContain('rede sem fio')
  })

  it('indenta pela profundidade', () => {
    const wrapper = mountRow(ROW, 2)
    const span = wrapper.find('[data-testid="service-leaf-name"]').element.parentElement as HTMLElement
    expect(span.style.paddingLeft).toBe('2.5rem') // depth 2 * 1.25rem
  })

  it('mostra "Invalidar" apenas quando ValidID=1', () => {
    const valid = mountRow({ ...ROW, ValidID: '1' })
    expect(valid.find('[data-testid="service-invalidate"]').exists()).toBe(true)

    const invalid = mountRow({ ...ROW, ValidID: '2' })
    expect(invalid.find('[data-testid="service-invalidate"]').exists()).toBe(false)
  })

  it('emite edit e invalidate ao clicar', async () => {
    const wrapper = mountRow()
    await wrapper.find('[data-testid="service-edit"]').trigger('click')
    expect(wrapper.emitted('edit')).toBeTruthy()
    await wrapper.find('[data-testid="service-invalidate"]').trigger('click')
    expect(wrapper.emitted('invalidate')).toBeTruthy()
  })

  it('mostra "—" quando não há comentário', () => {
    const wrapper = mountRow({ ...ROW, Comment: '' })
    expect(wrapper.text()).toContain('—')
  })
})
