import { describe, expect, it } from 'vitest'
import { glosaMeta } from '../components/contract/glosa'

describe('glosaMeta', () => {
  // Cores semânticas FIXAS do Nuxt UI (error≈vermelho, warning≈âmbar) — adaptam
  // light/dark e nunca usam a cor de marca (H8). Antes eram text-red-*/text-amber-*.
  it('approved -> strike, error (red), never brand', () => {
    const m = glosaMeta('approved')!
    expect(m.strike).toBe(true)
    expect(m.classes).toContain('error')
    expect(m.classes).not.toContain('brand')
  })
  it('pending -> warning (amber), not strike', () => {
    const m = glosaMeta('pending')!
    expect(m.strike).toBe(false)
    expect(m.classes).toContain('warning')
    expect(m.classes).not.toContain('brand')
  })
  it('null -> null', () => {
    expect(glosaMeta(null)).toBeNull()
  })
})
