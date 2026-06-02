import { describe, expect, it } from 'vitest'
import { DEFAULT_BRANDING, resolveSubdomain } from '../server/middleware/branding'

describe('branding middleware helpers', () => {
  it('derives subdomain from X-Forwarded-Host first', () => {
    expect(resolveSubdomain('aurora.suporte.gerti.com.br', '')).toBe('aurora')
    expect(resolveSubdomain('', 'aurora.suporte.gerti.com.br')).toBe('aurora')
    expect(resolveSubdomain('localhost', '')).toBeNull()
  })
  it('default branding is neutral, never "Gerti"', () => {
    expect(DEFAULT_BRANDING.display_name).toBe('Portal')
    expect(DEFAULT_BRANDING.display_name).not.toMatch(/gerti/i)
  })
  // #1F-a: *.suporte.was.dev.br (zona CF do token de teste) deve resolver
  // subdomain — mesma captura que *.suporte.gerti.com.br.
  it('resolves subdomain from *.suporte.was.dev.br (test CF zone)', () => {
    expect(resolveSubdomain('aurora.suporte.was.dev.br', '')).toBe('aurora')
    expect(resolveSubdomain('technova.suporte.was.dev.br', '')).toBe('technova')
    expect(resolveSubdomain('', 'aurora.suporte.was.dev.br')).toBe('aurora')
  })
  it('unknown host (neither zone) resolves to null → default branding', () => {
    expect(resolveSubdomain('aurora.suporte.evil.example.com', '')).toBeNull()
    expect(resolveSubdomain('aurora.suporte.other.io', '')).toBeNull()
  })
  // #1F-a: 1-nível <sub>.was.dev.br (Universal SSL *.was.dev.br)
  it('resolves subdomain from 1-level <sub>.was.dev.br', () => {
    expect(resolveSubdomain('aurora.was.dev.br', '')).toBe('aurora')
    expect(resolveSubdomain('technova.was.dev.br', '')).toBe('technova')
    expect(resolveSubdomain('', 'aurora.was.dev.br')).toBe('aurora')
  })
  it('infra was.dev.br hosts resolve to null → default branding', () => {
    expect(resolveSubdomain('znuny-dev.was.dev.br', '')).toBeNull()
    expect(resolveSubdomain('api-dev.was.dev.br', '')).toBeNull()
    expect(resolveSubdomain('groundcontrol.was.dev.br', '')).toBeNull()
  })
  it('suffix-injection aurora.was.dev.br.evil.com resolves to null', () => {
    expect(resolveSubdomain('aurora.was.dev.br.evil.com', '')).toBeNull()
  })
  it('bare was.dev.br (no sub) resolves to null', () => {
    expect(resolveSubdomain('was.dev.br', '')).toBeNull()
  })
})
