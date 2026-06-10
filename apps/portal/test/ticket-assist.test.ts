import { describe, expect, it } from 'vitest'
import { applyAssistResult, shouldShowAssistButton } from '../components/ticket/assist'

// #1S — assistente de escrita de chamado por IA.
//
// HARNESS: mesmo padrão de ticketing-flow.test.ts / assets-flow.test.ts — testes
// de lógica PURA (plain vitest), SEM montar a page (que usa <script setup> +
// composables Nuxt). A lógica testável vive em components/ticket/assist.ts.
//
// COBERTURA:
//   ✓ shouldShowAssistButton: visível só com ai_assist_enabled E body não-vazio.
//   ✓ applyAssistResult: popula title+body do form (rascunho editável; nunca
//     auto-submete). Saída tratada como texto (renderizada escapada nos inputs).

describe('shouldShowAssistButton: visibilidade do botão Melhorar com IA', () => {
  it('feature off → oculto mesmo com corpo preenchido', () => {
    expect(shouldShowAssistButton(false, 'tem texto')).toBe(false)
  })
  it('feature on mas corpo vazio → oculto', () => {
    expect(shouldShowAssistButton(true, '   ')).toBe(false)
    expect(shouldShowAssistButton(true, '')).toBe(false)
  })
  it('feature on e corpo preenchido → visível', () => {
    expect(shouldShowAssistButton(true, 'a impressora parou')).toBe(true)
  })
  it('flag undefined → oculto (default seguro)', () => {
    expect(shouldShowAssistButton(undefined, 'texto')).toBe(false)
  })
})

describe('applyAssistResult: popula o rascunho (nunca auto-submete)', () => {
  it('aplica title e body retornados', () => {
    const form = { title: 'orig', body: 'orig body' }
    applyAssistResult(form, { title: 'Novo título', body: 'Nova descrição estruturada' })
    expect(form.title).toBe('Novo título')
    expect(form.body).toBe('Nova descrição estruturada')
  })
  it('title vazio na resposta → mantém o título atual', () => {
    const form = { title: 'mantido', body: 'x' }
    applyAssistResult(form, { title: '', body: 'corpo novo' })
    expect(form.title).toBe('mantido')
    expect(form.body).toBe('corpo novo')
  })
  it('não muta nada além de title/body', () => {
    const form = { title: 'a', body: 'b', extra: 'preservado' } as Record<string, string>
    applyAssistResult(form as { title: string, body: string }, { title: 'A', body: 'B' })
    expect(form.extra).toBe('preservado')
  })
})
