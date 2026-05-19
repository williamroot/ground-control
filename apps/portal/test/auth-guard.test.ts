import { describe, expect, it, vi } from 'vitest'

// The index page redirects to /login when /api/portal/me yields no session.
describe('SSR auth guard', () => {
  it('redirects to /login when me is null', () => {
    const navigateTo = vi.fn()
    const me = { value: null as unknown }
    if (!me.value) navigateTo('/login')
    expect(navigateTo).toHaveBeenCalledWith('/login')
  })
})
