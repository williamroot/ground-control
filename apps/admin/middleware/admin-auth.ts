// Guarda de rota por sessão admin (Spec #1G-a). STUB da Fase 0 — T1.E preenche
// (busca /api/admin/me; sem sessão → redireciona /login). Por ora é no-op para
// o scaffold compilar; aplicada via definePageMeta nas páginas autenticadas.
export default defineNuxtRouteMiddleware(() => {
  // T1.E: const { data } = await useAdmin(); if (!data.value) return navigateTo('/login')
})
