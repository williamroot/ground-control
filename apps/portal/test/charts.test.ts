import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AreaChart from '../components/charts/AreaChart.vue'
import BarChart from '../components/charts/BarChart.vue'
import DonutChart from '../components/charts/DonutChart.vue'
import ProgressBar from '../components/charts/ProgressBar.vue'

describe('ProgressBar', () => {
  it('clamps percent to 100 and uses brand var', () => {
    const w = mount(ProgressBar, { props: { percent: 250 } })
    const html = w.html()
    expect(html).toContain('var(--brand-primary)')
    // width never exceeds 100%
    expect(html).toMatch(/width:\s*100%/)
  })
  it('renders 0% for null percent without throwing', () => {
    const w = mount(ProgressBar, { props: { percent: null } })
    expect(w.html()).toMatch(/width:\s*0%/)
  })
})

describe('AreaChart', () => {
  it('renders an empty state when no points', () => {
    const w = mount(AreaChart, { props: { points: [] } })
    expect(w.text()).toContain('Sem dados')
  })
  it('emits an svg path from points and uses brand var', () => {
    const w = mount(AreaChart, {
      props: { points: [
        { bucket: '2026-01-01', value: 0 },
        { bucket: '2026-01-02', value: 2 },
        { bucket: '2026-01-03', value: 1 },
      ] },
    })
    const html = w.html()
    expect(html).toContain('<path')
    expect(html).toContain('var(--brand-primary)')
    // SSR-safe: fixed viewBox, no width/height pixel binding from window
    expect(html).toContain('viewBox')
  })
})

describe('BarChart', () => {
  it('renders one rect per bar, uses brand var, SSR-safe viewBox', () => {
    const w = mount(BarChart, {
      props: { bars: [
        { label: '1', value: 2 },
        { label: '2', value: 5 },
        { label: '3', value: 0 },
      ] },
    })
    const html = w.html()
    const rects = html.match(/<rect/g) ?? []
    // 3 bars (zero-value bars still render a rect with min height)
    expect(rects.length).toBe(3)
    expect(html).toContain('var(--brand-primary)')
    expect(html).toContain('viewBox')
  })
  it('renders empty state when no bars', () => {
    const w = mount(BarChart, { props: { bars: [] } })
    expect(w.text()).toContain('Sem dados')
  })
})

describe('DonutChart', () => {
  it('renders one slice per segment, proportional, SSR-safe', () => {
    const w = mount(DonutChart, {
      props: { segments: [
        { label: 'open', value: 3 },
        { label: 'closed', value: 7 },
      ] },
    })
    const html = w.html()
    const paths = html.match(/<path/g) ?? []
    expect(paths.length).toBe(2)
    expect(html).toContain('viewBox')
    // brand palette by default
    expect(html).toContain('var(--brand-primary)')
  })
  it('uses SEMANTIC colors (not brand) when palette=semantic (H8)', () => {
    const w = mount(DonutChart, {
      props: {
        palette: 'semantic',
        segments: [
          { label: 'SLA estourado', value: 2, tone: 'error' },
          { label: 'ok', value: 8, tone: 'success' },
        ],
      },
    })
    const html = w.html()
    // semantic tones map to CSS semantic vars, never the brand var
    expect(html).toContain('var(--color-error)')
    expect(html).toContain('var(--color-success)')
    expect(html).not.toContain('var(--brand-primary)')
  })
  it('renders empty state when no segments', () => {
    const w = mount(DonutChart, { props: { segments: [] } })
    expect(w.text()).toContain('Sem dados')
  })
  it('desenha um ANEL completo para uma fatia única de 100% (não degenera o arco de 360°)', () => {
    // Regressão: arco de 360° tem início == fim (12h) → path degenerado, nada
    // é desenhado. Acontecia quando todos os tickets estavam num só estado.
    const w = mount(DonutChart, { props: { segments: [{ label: 'new', value: 10 }] } })
    const path = w.find('path')
    expect(path.exists()).toBe(true)
    // anel completo vaza o miolo com fill-rule evenodd
    expect(path.attributes('fill-rule')).toBe('evenodd')
    const d = path.attributes('d') ?? ''
    // path real (dois arcos externos + dois internos), não um arco degenerado
    expect((d.match(/A/g) ?? []).length).toBeGreaterThanOrEqual(4)
  })
})
