import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AreaChart from '../components/charts/AreaChart.vue'
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
