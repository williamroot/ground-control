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
})
