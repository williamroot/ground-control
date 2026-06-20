export default defineNuxtConfig({
  ssr: true,
  modules: ['@nuxt/ui', '@nuxt/eslint'],
  app: {
    head: {
      title: 'Contratar — Gerti',
      link: [{ rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' }],
    },
  },
  colorMode: { preference: 'light', fallback: 'light' },
  components: [{ path: '~/components', pathPrefix: false }],
  css: ['~/assets/css/main.css'],
  runtimeConfig: {
    // O checkout é PÚBLICO e cross-tenant: fala com o sidecar em /v1/checkout/*.
    sidecarUrl: process.env.SIDECAR_URL || 'http://sidecar:8001',
  },
  fonts: {
    families: [
      { name: 'Bricolage Grotesque', provider: 'google', weights: [400, 600, 700, 800] },
      { name: 'Hanken Grotesk', provider: 'google', weights: [400, 500, 600, 700] },
    ],
  },
  devtools: { enabled: false },
  compatibilityDate: '2026-05-17',
})
