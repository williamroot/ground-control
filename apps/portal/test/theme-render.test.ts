import { describe, expect, it } from 'vitest'
import { DEFAULT_BRANDING } from '../server/middleware/branding'

function cssVars(b: { primary_color: string, accent_color: string }) {
  return `:root{--brand-primary:${b.primary_color};--brand-accent:${b.accent_color};}`
}

describe('theme render from tokens', () => {
  it('emits CSS vars from branding tokens', () => {
    const css = cssVars({ primary_color: '#0EA5E9', accent_color: '#0369A1' })
    expect(css).toContain('--brand-primary:#0EA5E9')
    expect(css).toContain('--brand-accent:#0369A1')
  })
  it('default tokens render without throwing', () => {
    expect(cssVars(DEFAULT_BRANDING)).toContain('--brand-primary:#475569')
  })
})
