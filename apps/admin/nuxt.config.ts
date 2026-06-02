export default defineNuxtConfig({
  ssr: true,
  modules: ['@nuxt/ui', '@pinia/nuxt', '@nuxt/eslint'],
  // Console de Administração (Spec #1G-a): identidade FIXA Gerti/WAS — NÃO é o
  // portal white-label do cliente. As cores da marca vêm do main.css (não há
  // branding por-tenant aqui). Tema claro/escuro/sistema como no portal.
  colorMode: {
    preference: 'system',
    fallback: 'light',
  },
  components: [{ path: '~/components', pathPrefix: false }],
  css: ['~/assets/css/main.css'],
  runtimeConfig: {
    sidecarUrl: process.env.SIDECAR_URL || 'http://sidecar:8001',
    public: {
      // Subdomínio do console (gerti.was.dev.br em teste; admin.suporte.gerti.com.br em prod).
      adminBaseDomain: process.env.ADMIN_BASE_DOMAIN || 'gerti.was.dev.br',
    },
  },
  fonts: {
    families: [
      { name: 'Bricolage Grotesque', provider: 'google', weights: [400, 600, 700, 800] },
      { name: 'Hanken Grotesk', provider: 'google', weights: [400, 500, 600, 700] },
    ],
  },
  devtools: { enabled: false },
  compatibilityDate: '2026-06-02',
})
