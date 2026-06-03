// Guarda de rota por sessão admin (Spec #1G-a, T1.E). Middleware NOMEADA
// (aplicada via definePageMeta nas páginas autenticadas) — não roda no /login.
// Sem sessão válida (`gsid_adm`) → redireciona para /login.
export default defineNuxtRouteMiddleware(async (to) => {
  if ((to?.path ?? '/') === '/login') return

  const { data } = await useAdmin()
  if (!data.value) return navigateTo('/login')
})
