// @vitest-environment nuxt
//
// #1F-a regression — fecha o gap que os testes de unidade (só resolveSubdomain)
// nunca cobriram: a CADEIA layout → branding em SSR.
//
// Abordagem ESCOLHIDA: (b) teste de integração focado que RENDERIZA o SFC
// layouts/default.vue no runtime Nuxt (ambiente vitest `nuxt`, in-process, SEM
// bootar o servidor Nitro e SEM rede), com os composables auto-importados do
// Nuxt mockados via mockNuxtImport — o caminho idiomático do Nuxt 3.
//
// Por quê (b) e não (a) @nuxt/test-utils/e2e: um e2e real subiria o servidor
// Nitro + exigiria um mock server do sidecar (o middleware de branding chama
// o sidecar via sidecarFetch) — pesado e flaky neste ambiente offline.
// mountSuspended + mockNuxtImport exercita o MESMO código do layout de forma
// determinística e green, sem dependência de rede.
//
// O que isto PROVA (e que falharia contra o $fetch('/api/branding-context')
// antigo — aquele lia de uma sub-request que perde o Host do tenant):
//   1. O layout LÊ event.context.branding (a request ORIGINAL, com o Host do
//      tenant que o middleware resolveu) e renderiza o branding do tenant
//      (Aurora) — NÃO o DEFAULT.
//   2. Sem branding no context, cai no DEFAULT_BRANDING.
//   3. useRequestEvent é o canal de leitura — não há $fetch interno de branding.
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { clearNuxtState } from '#imports'
import DefaultLayout from '../layouts/default.vue'
import { DEFAULT_BRANDING, type Branding } from '../server/middleware/branding'

const AURORA: Branding = {
  display_name: 'Aurora Móveis',
  logo_url: null,
  primary_color: '#7C3AED',
  accent_color: '#5B21B6',
  default_theme: 'light',
  support_email: 'suporte@aurora.example',
}

const { useRequestEventMock } = vi.hoisted(() => ({ useRequestEventMock: vi.fn() }))
mockNuxtImport('useRequestEvent', () => useRequestEventMock)

afterEach(() => {
  useRequestEventMock.mockReset()
  // useState('branding') é keyed pela app Nuxt compartilhada entre testes; o
  // factory só roda uma vez por chave. Limpar garante isolamento por teste.
  clearNuxtState('branding')
})

describe('#1F-a SSR layout reads branding from event.context (no host-losing sub-request)', () => {
  it('renders tenant branding from event.context.branding (Aurora, not DEFAULT)', async () => {
    useRequestEventMock.mockReturnValue({ context: { branding: AURORA } })
    const wrapper = await mountSuspended(DefaultLayout)
    expect(wrapper.text()).toContain('Aurora Móveis')
    expect(wrapper.text()).not.toContain('Portal')
    expect(wrapper.text()).toContain('suporte@aurora.example')
  })

  it('falls back to DEFAULT_BRANDING when event has no branding context', async () => {
    useRequestEventMock.mockReturnValue({ context: {} })
    const wrapper = await mountSuspended(DefaultLayout)
    expect(wrapper.text()).toContain(DEFAULT_BRANDING.display_name) // "Portal"
    expect(wrapper.text()).not.toContain('Aurora')
  })

  it('falls back to DEFAULT_BRANDING when useRequestEvent is undefined (client hydration guard)', async () => {
    useRequestEventMock.mockReturnValue(undefined)
    const wrapper = await mountSuspended(DefaultLayout)
    expect(wrapper.text()).toContain(DEFAULT_BRANDING.display_name)
  })
})
