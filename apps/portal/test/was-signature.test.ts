import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WasSignature from '../components/WasSignature.vue'

describe('WasSignature', () => {
  it('shows the WAS credit, muted, never brand', () => {
    const w = mount(WasSignature)
    const html = w.html()
    expect(w.text()).toContain('WAS Soluções em Tecnologia')
    expect(html).toContain('text-xs')
    expect(html).not.toContain('--brand-primary')
    expect(html).not.toContain('--brand-accent')
  })
})
