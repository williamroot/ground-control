// Guarda de sessão + papel — Spec #1H. Middleware NOMEADA (aplicada via
// definePageMeta nas páginas autenticadas) — não roda no /login nem em mounts
// isolados de layout/componentes.
//  • sem sessão: redireciona /login.
//  • rotas admin-only (/ e /contratos/...): help-desk é mandado p/ /tickets.
//  • /tickets: liberado para qualquer sessão (home do help-desk; placeholder #1E).
// Least-privilege: na dúvida (role != admin) não mostra contratos/valores.
export default defineNuxtRouteMiddleware(async (to) => {
  const path = to?.path ?? '/'
  if (path === '/login') return

  const { data: me } = await useMe()
  if (!me.value) return navigateTo('/login')

  // Spec #3: /base-conhecimento, /catalogo, /notificacoes, /perfil e /busca
  // são liberadas para QUALQUER papel autenticado — de propósito NÃO entram
  // neste predicado (não use startsWith aqui sem checar contra essa lista).
  const adminOnly = path === '/' || path.startsWith('/contratos')
  if (adminOnly && me.value.role !== 'admin') return navigateTo('/tickets')
})
