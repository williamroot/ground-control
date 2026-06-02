export default defineNuxtConfig({
  ssr: true,
  modules: ['@nuxt/ui', '@pinia/nuxt', '@nuxt/eslint'],
  // Tema claro/escuro/sistema com toggle na UI (ThemeToggle.vue). `system` é o
  // default (segue o SO); a escolha do usuário persiste via @nuxtjs/color-mode.
  // O fallback é light para SSR/sem-JS. As cores das páginas usam tokens
  // semânticos do Nuxt UI (bg-default/text-muted/border-default…) que viram no
  // `.dark`, então o design white-label fica coerente nos dois modos.
  colorMode: {
    preference: 'system',
    fallback: 'light',
  },
  components: [{ path: '~/components', pathPrefix: false }],
  // #1F-a: entry CSS do Nuxt UI v3 / Tailwind v4 (Tailwind + tema Nuxt UI +
  // fontes da marca). Sem isto as utilities não entram no build.
  css: ['~/assets/css/main.css'],
  runtimeConfig: {
    sidecarUrl: process.env.SIDECAR_URL || 'http://sidecar:8001',
    public: {
      baseDomain: process.env.PORTAL_BASE_DOMAIN || 'suporte.gerti.com.br',
    },
  },
  // @nuxt/fonts já vem com o @nuxt/ui v3; só declaramos as famílias da marca.
  fonts: {
    families: [
      { name: 'Bricolage Grotesque', provider: 'google', weights: [400, 600, 700, 800] },
      { name: 'Hanken Grotesk', provider: 'google', weights: [400, 500, 600, 700] },
    ],
  },
  devtools: { enabled: false },
  compatibilityDate: '2026-05-17',
})
