export default defineNuxtConfig({
  ssr: true,
  modules: ['@nuxt/ui', '@pinia/nuxt', '@nuxt/eslint'],
  runtimeConfig: {
    sidecarUrl: process.env.SIDECAR_URL || 'http://sidecar:8001',
    public: {
      baseDomain: process.env.PORTAL_BASE_DOMAIN || 'suporte.gerti.com.br',
    },
  },
  devtools: { enabled: false },
  compatibilityDate: '2026-05-17',
})
