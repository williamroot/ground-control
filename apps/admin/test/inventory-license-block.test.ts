// Caso da Georgia (teste V01): licença só com `tickets` e exigência ligada. O
// sidecar responde 403 nas rotas de inventário; a página tem que virar
// BLOQUEIO, nunca "Nenhum dispositivo" (que parece vazio, não bloqueado).
import { describe, expect, it } from 'vitest'
import {
  anyBlocked,
  failureOutcome,
  httpStatusOf,
  INVENTORY_BLOCKED_HINT,
  INVENTORY_BLOCKED_TITLE,
  isModuleBlocked,
  okOutcome,
  outcomeData,
} from '../composables/useAgents'

// Forma do erro do ofetch/$fetch quando o proxy devolve 403.
const forbidden = { statusCode: 403, data: { detail: 'licença sem o módulo \'inventory\'' } }

describe('httpStatusOf / isModuleBlocked', () => {
  it('lê o status nas três formas do ofetch', () => {
    expect(httpStatusOf({ statusCode: 403 })).toBe(403)
    expect(httpStatusOf({ status: 403 })).toBe(403)
    expect(httpStatusOf({ response: { status: 403 } })).toBe(403)
    expect(httpStatusOf(new Error('rede'))).toBeNull()
    expect(httpStatusOf(null)).toBeNull()
  })

  it('403 é bloqueio de módulo', () => {
    expect(isModuleBlocked(forbidden)).toBe(true)
    // O proxy fino devolve null no corpo: o status basta.
    expect(isModuleBlocked({ statusCode: 403, data: null })).toBe(true)
  })

  it('401, 404, 500 e falha de rede NÃO são bloqueio', () => {
    for (const statusCode of [401, 404, 500, 503]) expect(isModuleBlocked({ statusCode })).toBe(false)
    expect(isModuleBlocked(new TypeError('fetch failed'))).toBe(false)
  })
})

describe('outcomes de carga', () => {
  it('403 vira blocked; o resto vira error', () => {
    expect(failureOutcome(forbidden)).toEqual({ status: 'blocked' })
    expect(failureOutcome({ statusCode: 500 })).toEqual({ status: 'error' })
  })

  it('basta uma carga bloqueada para bloquear a página', () => {
    expect(anyBlocked(okOutcome([]), failureOutcome(forbidden))).toBe(true)
    expect(anyBlocked(okOutcome([]), failureOutcome({ statusCode: 500 }))).toBe(false)
    expect(anyBlocked(null, undefined)).toBe(false)
  })

  it('lista vazia de verdade continua vazia (não bloqueada)', () => {
    expect(anyBlocked(okOutcome([]), okOutcome([]))).toBe(false)
    expect(outcomeData(okOutcome([]))).toEqual([])
  })

  it('bloqueado ou erro não tem dados', () => {
    expect(outcomeData(failureOutcome(forbidden))).toBeNull()
    expect(outcomeData(failureOutcome({ statusCode: 500 }))).toBeNull()
    expect(outcomeData(null)).toBeNull()
  })

  it('outcome é JSON puro (vai no payload do SSR)', () => {
    const o = failureOutcome(forbidden)
    expect(JSON.parse(JSON.stringify(o))).toEqual(o)
  })
})

describe('textos do bloqueio', () => {
  it('dizem o módulo e o próximo passo', () => {
    expect(INVENTORY_BLOCKED_TITLE).toBe('Sua licença não inclui o módulo Inventário')
    expect(INVENTORY_BLOCKED_HINT).toBe('Peça a um administrador para incluir o módulo em Licenças.')
  })
})
