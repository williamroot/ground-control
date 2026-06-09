// #1N Task 6 — AiPanel: painel de IA no detalhe do atendimento.
// Componente em HTML/SVG nativo (sem U*/@nuxt/icon) para montar limpo no vitest
// (lição do #1M: auto-import de componentes Nuxt quebra com [nuxt] instance
// unavailable). Testamos: render condicional por aiEnabled, botões, loading,
// e emissão de use-draft com o texto do rascunho.
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AiPanel from '../components/AiPanel.vue'

describe('AiPanel', () => {
  it('não renderiza nada quando aiEnabled=false (kill-switch)', () => {
    const wrapper = mount(AiPanel, { props: { ticketId: 42, aiEnabled: false } })
    expect(wrapper.find('[data-testid="ai-panel"]').exists()).toBe(false)
  })

  it('mostra os dois botões quando aiEnabled=true', () => {
    const wrapper = mount(AiPanel, { props: { ticketId: 42, aiEnabled: true } })
    expect(wrapper.find('[data-testid="ai-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ai-summarize"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ai-suggest"]').exists()).toBe(true)
  })

  it('exibe estado de carregamento e desabilita os botões', async () => {
    const wrapper = mount(AiPanel, {
      props: { ticketId: 42, aiEnabled: true, loading: true },
    })
    const btn = wrapper.find('[data-testid="ai-summarize"]')
    expect((btn.element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.find('[data-testid="ai-loading"]').exists()).toBe(true)
  })

  it('renderiza o resultado escapado (sem v-html) e emite use-draft no resultado de resposta', async () => {
    const wrapper = mount(AiPanel, {
      props: {
        ticketId: 42,
        aiEnabled: true,
        result: { kind: 'reply', text: 'Olá <b>cliente</b>, [VERIFICAR]' },
      },
    })
    const out = wrapper.find('[data-testid="ai-result"]')
    expect(out.exists()).toBe(true)
    // texto cru exibido (o HTML do LLM aparece como texto, não interpretado)
    expect(out.text()).toContain('<b>cliente</b>')
    expect(out.html()).not.toContain('<b>cliente</b>') // não foi injetado como markup
    // botão "usar como rascunho" só no resultado de resposta
    const use = wrapper.find('[data-testid="ai-use-draft"]')
    expect(use.exists()).toBe(true)
    await use.trigger('click')
    expect(wrapper.emitted('use-draft')?.[0]).toEqual(['Olá <b>cliente</b>, [VERIFICAR]'])
  })

  it('resultado de resumo NÃO mostra "usar como rascunho"', () => {
    const wrapper = mount(AiPanel, {
      props: {
        ticketId: 42,
        aiEnabled: true,
        result: { kind: 'summary', text: 'Resumo factual.' },
      },
    })
    expect(wrapper.find('[data-testid="ai-result"]').text()).toContain('Resumo factual.')
    expect(wrapper.find('[data-testid="ai-use-draft"]').exists()).toBe(false)
  })

  it('emite summarize/suggest ao clicar nos botões', async () => {
    const wrapper = mount(AiPanel, { props: { ticketId: 42, aiEnabled: true } })
    await wrapper.find('[data-testid="ai-summarize"]').trigger('click')
    await wrapper.find('[data-testid="ai-suggest"]').trigger('click')
    expect(wrapper.emitted('summarize')).toBeTruthy()
    expect(wrapper.emitted('suggest')).toBeTruthy()
  })
})
