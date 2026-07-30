import { describe, expect, it } from 'vitest'
import { CATALOG_ICON_ALLOWLIST, catalogIconName } from '../components/catalog/catalog-icons'

// Spec #3 · V2 — mapa de ícones do catálogo de serviços. O backend valida a
// mesma allowlist no `icon` do item (422 fora dela); aqui replicamos o guard
// no front para nunca resolver um nome de ícone fora do controle do design
// system, mesmo que o dado chegue inesperado.

describe('catalogIconName: allowlist estrita → i-lucide-*', () => {
  it('cada ícone da allowlist mapeia para i-lucide-<nome>', () => {
    for (const icon of CATALOG_ICON_ALLOWLIST) {
      expect(catalogIconName(icon)).toBe(`i-lucide-${icon}`)
    }
  })

  it('é case-insensitive e tolera espaços nas bordas', () => {
    expect(catalogIconName('Server')).toBe('i-lucide-server')
    expect(catalogIconName('  mail  ')).toBe('i-lucide-mail')
  })

  it('fora da allowlist → fallback i-lucide-ticket', () => {
    expect(catalogIconName('rocket')).toBe('i-lucide-ticket')
    expect(catalogIconName('trash')).toBe('i-lucide-ticket')
    expect(catalogIconName('<script>alert(1)</script>')).toBe('i-lucide-ticket')
  })

  it('null/undefined/vazio → fallback', () => {
    expect(catalogIconName(null)).toBe('i-lucide-ticket')
    expect(catalogIconName(undefined)).toBe('i-lucide-ticket')
    expect(catalogIconName('')).toBe('i-lucide-ticket')
  })

  it('a allowlist bate exatamente com a do backend (V2)', () => {
    expect([...CATALOG_ICON_ALLOWLIST].sort()).toEqual(
      ['ticket', 'shield', 'user-plus', 'server', 'package', 'database', 'box', 'printer', 'lock', 'wifi', 'mail', 'settings'].sort(),
    )
  })
})
