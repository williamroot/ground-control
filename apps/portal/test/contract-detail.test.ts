import { describe, expect, it } from 'vitest'
import { glosaMeta } from '../components/contract/glosa'

describe('glosaMeta', () => {
  it('approved -> strike, red, never brand', () => {
    const m = glosaMeta('approved')!
    expect(m.strike).toBe(true)
    expect(m.classes).toContain('red')
    expect(m.classes).not.toContain('brand')
  })
  it('pending -> amber, not strike', () => {
    const m = glosaMeta('pending')!
    expect(m.strike).toBe(false)
    expect(m.classes).toContain('amber')
  })
  it('null -> null', () => {
    expect(glosaMeta(null)).toBeNull()
  })
})
