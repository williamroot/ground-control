import { describe, expect, it } from 'vitest'

// Espelha a decisão da guarda global (middleware/auth.global.ts, #1H) e da nav
// por papel do layout — mesmo padrão de teste de lógica do auth-guard.test.ts.

type Role = 'admin' | 'helpdesk'

function guardRedirect(path: string, me: { role: Role } | null): string | null {
  if (path === '/login') return null
  if (!me) return '/login'
  const adminOnly = path === '/' || path.startsWith('/contratos')
  if (adminOnly && me.role !== 'admin') return '/tickets'
  return null
}

function navItems(role?: Role): string[] {
  const items: string[] = []
  if (role === 'admin') items.push('Contratos')
  if (role) items.push('Tickets')
  return items
}

describe('guarda global por papel (#1H)', () => {
  it('/login é sempre liberado', () => {
    expect(guardRedirect('/login', null)).toBeNull()
  })
  it('sem sessão em rota protegida -> /login', () => {
    expect(guardRedirect('/', null)).toBe('/login')
    expect(guardRedirect('/contratos/abc', null)).toBe('/login')
    expect(guardRedirect('/tickets', null)).toBe('/login')
  })
  it('admin acessa contratos e dashboard', () => {
    expect(guardRedirect('/', { role: 'admin' })).toBeNull()
    expect(guardRedirect('/contratos/abc', { role: 'admin' })).toBeNull()
  })
  it('help-desk é mandado para /tickets nas rotas admin-only', () => {
    expect(guardRedirect('/', { role: 'helpdesk' })).toBe('/tickets')
    expect(guardRedirect('/contratos/abc', { role: 'helpdesk' })).toBe('/tickets')
  })
  it('/tickets é liberado para ambos os papéis', () => {
    expect(guardRedirect('/tickets', { role: 'helpdesk' })).toBeNull()
    expect(guardRedirect('/tickets', { role: 'admin' })).toBeNull()
  })
})

describe('nav por papel (#1H)', () => {
  it('admin vê Contratos + Tickets', () => {
    expect(navItems('admin')).toEqual(['Contratos', 'Tickets'])
  })
  it('help-desk vê só Tickets (sem Contratos)', () => {
    expect(navItems('helpdesk')).toEqual(['Tickets'])
  })
  it('sem papel não mostra nav', () => {
    expect(navItems(undefined)).toEqual([])
  })
})
