import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CsatPrompt from '../components/ticket/CsatPrompt.vue'

// CsatPrompt é um componente puro (HTML + SVG inline), sem Nuxt UI — montável
// direto, como WasSignature/charts.

describe('CsatPrompt', () => {
  it('renders 5 score buttons', () => {
    const w = mount(CsatPrompt)
    expect(w.findAll('[data-csat-score]').length).toBe(5)
  })

  it('emits submit with the selected score and comment', async () => {
    const w = mount(CsatPrompt)
    // seleciona nota 4
    await w.findAll('[data-csat-score]')[3]!.trigger('click')
    // escreve comentário
    await w.find('textarea').setValue('muito bom')
    // envia
    await w.find('[data-csat-submit]').trigger('click')
    const emitted = w.emitted('submit')
    expect(emitted).toBeTruthy()
    const payload = emitted![0]![0] as { score: number, comment: string }
    expect(payload.score).toBe(4)
    expect(payload.comment).toBe('muito bom')
  })

  it('does not submit without a selected score', async () => {
    const w = mount(CsatPrompt)
    await w.find('[data-csat-submit]').trigger('click')
    expect(w.emitted('submit')).toBeFalsy()
  })

  it('uses semantic colors, never the brand var (H8)', () => {
    const w = mount(CsatPrompt)
    const html = w.html()
    expect(html).not.toContain('--brand-primary')
    expect(html).not.toContain('--brand-accent')
    // escala semântica presente
    expect(html).toMatch(/text-(error|warning|success|muted|dimmed)/)
  })

  it('shows the answered state (score, no form) when submitted prop is set', () => {
    const w = mount(CsatPrompt, { props: { submittedScore: 5 } })
    expect(w.find('[data-csat-submit]').exists()).toBe(false)
    expect(w.find('[data-csat-answered]').exists()).toBe(true)
    expect(w.text()).toMatch(/5\/5/)
  })
})
