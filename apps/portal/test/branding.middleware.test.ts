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
})
