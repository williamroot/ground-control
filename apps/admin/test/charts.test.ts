// Charts copiados do portal (#1O) — apps não compartilham bundle, então os
// componentes SVG vivem nos dois. Mesmo contrato: SVG nativo, brand/semântico,
// SSR-safe (viewBox fixo). H8: estados em cores semânticas, marca só identidade.
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import BarChart from '../components/charts/BarChart.vue'
import DonutChart from '../components/charts/DonutChart.vue'

describe('BarChart (admin bundle)', () => {
  it('renders one rect per bar, uses brand var, SSR-safe viewBox', () => {
    const w = mount(BarChart, {
      props: { bars: [
        { label: '1', value: 2 },
        { label: '2', value: 5 },
      ] },
    })
    const html = w.html()
    expect((html.match(/<rect/g) ?? []).length).toBe(2)
    expect(html).toContain('var(--brand-primary)')
    expect(html).toContain('viewBox')
  })
})

describe('DonutChart (admin bundle)', () => {
  it('renders one slice per segment (brand palette default)', () => {
    const w = mount(DonutChart, {
      props: { segments: [
        { label: 'open', value: 3 },
        { label: 'closed', value: 7 },
      ] },
    })
    const html = w.html()
    expect((html.match(/<path/g) ?? []).length).toBe(2)
    expect(html).toContain('var(--brand-primary)')
  })
  it('uses SEMANTIC colors when palette=semantic (H8)', () => {
    const w = mount(DonutChart, {
      props: {
        palette: 'semantic',
        segments: [
          { label: 'estourado', value: 2, tone: 'error' },
          { label: 'ok', value: 8, tone: 'success' },
        ],
      },
    })
    const html = w.html()
    expect(html).toContain('var(--color-error)')
    expect(html).not.toContain('var(--brand-primary)')
  })
  it('desenha um ANEL completo para fatia única de 100% (regressão arco 360°)', () => {
    const w = mount(DonutChart, { props: { segments: [{ label: 'new', value: 5 }] } })
    const path = w.find('path')
    expect(path.exists()).toBe(true)
    expect(path.attributes('fill-rule')).toBe('evenodd')
    expect(((path.attributes('d') ?? '').match(/A/g) ?? []).length).toBeGreaterThanOrEqual(4)
  })
})
