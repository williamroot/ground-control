// Spec #4 — guard da allowlist de objetos genéricos do Znuny e do formato de
// id, usado pelos 4 proxies `server/api/admin/znuny/objects/[object]/**`.
// Testado isoladamente (lógica pura) — é a parte de risco desses proxies:
// objeto fora da tabela ou id malformado tem que virar 400 sem chamar o
// sidecar (defesa em profundidade, o Perl também valida).
import { describe, expect, it } from 'vitest'
import { isNumericId, isZnunyObjectKey, ZNUNY_OBJECT_KEYS } from '../server/utils/znuny'

describe('isZnunyObjectKey', () => {
  it('aceita as 6 chaves do Bloco A', () => {
    for (const key of ZNUNY_OBJECT_KEYS) {
      expect(isZnunyObjectKey(key)).toBe(true)
    }
  })

  it('rejeita chave fora da allowlist', () => {
    expect(isZnunyObjectKey('Ticket')).toBe(false)
    expect(isZnunyObjectKey('CIClass')).toBe(false)
    expect(isZnunyObjectKey('queue')).toBe(false) // case-sensitive
  })

  it('rejeita vazio/undefined/null', () => {
    expect(isZnunyObjectKey('')).toBe(false)
    expect(isZnunyObjectKey(undefined)).toBe(false)
    expect(isZnunyObjectKey(null)).toBe(false)
  })
})

describe('isNumericId', () => {
  it('aceita dígitos', () => {
    expect(isNumericId('1')).toBe(true)
    expect(isNumericId('42')).toBe(true)
  })

  it('rejeita não numérico, vazio ou undefined', () => {
    expect(isNumericId('abc')).toBe(false)
    expect(isNumericId('1;drop table')).toBe(false)
    expect(isNumericId('1.5')).toBe(false)
    expect(isNumericId('-1')).toBe(false)
    expect(isNumericId('')).toBe(false)
    expect(isNumericId(undefined)).toBe(false)
  })
})
