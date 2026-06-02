// Fase 0 (#1G-a) smoke do scaffold: a identidade é FIXA Gerti (não white-label)
// e o cookie da sessão admin é DISTINTO do `gsid` do cliente. T1.E/T1.F
// substituem os placeholders e adicionam testes de login/onboarding.
import { describe, expect, it } from 'vitest'
import { ADMIN_COOKIE, ADMIN_IDENTITY } from '../shared/identity'

describe('scaffold do console admin', () => {
  it('identidade é Gerti, não white-label', () => {
    expect(ADMIN_IDENTITY.display_name).toContain('Gerti')
    expect(ADMIN_IDENTITY.primary_color).toMatch(/^#[0-9a-f]{6}$/i)
  })

  it('cookie da sessão admin é distinto do gsid do cliente', () => {
    expect(ADMIN_COOKIE).toBe('gsid_adm')
    expect(ADMIN_COOKIE).not.toBe('gsid')
  })
})
