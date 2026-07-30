// Spec #4 (Bloco A) — lógica pura da árvore de Serviços do Znuny. A guarda
// anti-ciclo é a parte com regra de verdade desta tela: nunca permitir que um
// serviço vire pai de si mesmo ou de um descendente seu.
import { describe, expect, it } from 'vitest'
import {
  buildServicePayload,
  buildInvalidateServicePayload,
  descendantIds,
  emptyServiceDraft,
  flattenServiceTree,
  invalidParentIds,
  leafName,
  parentOptions,
  buildServiceTree,
  serviceDraftFromRow,
  serviceRowFromItem,
  validateServiceDraft,
  type ServiceRow,
} from '../composables/useServiceTree'

function row(partial: Partial<ServiceRow> & { id: string, Name: string }): ServiceRow {
  return {
    ParentID: '',
    Comment: '',
    ValidID: '1',
    TypeID: '',
    Criticality: '',
    ...partial,
  }
}

const ROWS: ServiceRow[] = [
  row({ id: '1', Name: 'Suporte' }),
  row({ id: '2', Name: 'Suporte::Rede', ParentID: '1' }),
  row({ id: '3', Name: 'Suporte::Rede::Wi-Fi', ParentID: '2' }),
  row({ id: '4', Name: 'Infra' }),
  row({ id: '5', Name: 'Suporte::Impressoras', ParentID: '1' }),
]

describe('serviceRowFromItem', () => {
  it('normaliza um item cru (campos numéricos viram string, ausentes viram vazio)', () => {
    const item = { Name: 'Suporte::Rede', ParentID: 1, Comment: null, ValidID: 1, TypeID: 2, Criticality: '3 normal' }
    const r = serviceRowFromItem(item, '2')
    expect(r).toEqual({
      id: '2',
      Name: 'Suporte::Rede',
      ParentID: '1',
      Comment: '',
      ValidID: '1',
      TypeID: '2',
      Criticality: '3 normal',
    })
  })

  it('ValidID ausente cai no fallback "1"', () => {
    expect(serviceRowFromItem({ Name: 'X' }, '1').ValidID).toBe('1')
  })
})

describe('leafName', () => {
  it('extrai o último segmento de "Pai::Filho"', () => {
    expect(leafName('Suporte::Rede::Wi-Fi')).toBe('Wi-Fi')
    expect(leafName('Suporte')).toBe('Suporte')
    expect(leafName('')).toBe('')
  })
})

describe('buildServiceTree / flattenServiceTree', () => {
  it('agrupa por ParentID em níveis, ordenado por nome', () => {
    const tree = buildServiceTree(ROWS)
    expect(tree.map(n => n.row.id)).toEqual(['4', '1']) // Infra < Suporte alfabeticamente
    const suporte = tree.find(n => n.row.id === '1')!
    expect(suporte.children.map(n => n.row.id)).toEqual(['5', '2']) // Impressoras < Rede
    const rede = suporte.children.find(n => n.row.id === '2')!
    expect(rede.children.map(n => n.row.id)).toEqual(['3'])
    expect(rede.children[0]!.depth).toBe(2)
  })

  it('achata em pré-ordem preservando profundidade', () => {
    const flat = flattenServiceTree(buildServiceTree(ROWS))
    expect(flat.map(n => n.row.id)).toEqual(['4', '1', '5', '2', '3'])
    expect(flat.find(n => n.row.id === '3')!.depth).toBe(2)
    expect(flat.find(n => n.row.id === '1')!.depth).toBe(0)
  })

  it('não trava em ciclo de dado corrompido (A é pai de B que é pai de A)', () => {
    const cyclic: ServiceRow[] = [
      row({ id: 'a', Name: 'A', ParentID: 'b' }),
      row({ id: 'b', Name: 'B', ParentID: 'a' }),
    ]
    const tree = buildServiceTree(cyclic)
    // Nenhum dos dois aparece como raiz (ambos têm ParentID) — árvore fica vazia,
    // mas a função retorna em tempo finito (não trava o event loop).
    expect(tree).toEqual([])
  })
})

describe('descendantIds', () => {
  it('lista filhos e netos, não o próprio nó', () => {
    expect([...descendantIds(ROWS, '1')].sort()).toEqual(['2', '3', '5'])
    expect([...descendantIds(ROWS, '2')].sort()).toEqual(['3'])
    expect([...descendantIds(ROWS, '3')]).toEqual([])
  })
})

describe('invalidParentIds / parentOptions — guarda anti-ciclo', () => {
  it('ao criar (sem editingId), nada é bloqueado', () => {
    expect(invalidParentIds(ROWS, null).size).toBe(0)
    const options = parentOptions(ROWS, null)
    expect(options.map(o => o.value)).toContain('1')
    expect(options.map(o => o.value)).toContain('3')
  })

  it('bloqueia o próprio serviço como seu pai', () => {
    const blocked = invalidParentIds(ROWS, '1')
    expect(blocked.has('1')).toBe(true)
  })

  it('bloqueia todos os descendentes do serviço em edição', () => {
    const blocked = invalidParentIds(ROWS, '1')
    expect(blocked.has('2')).toBe(true)
    expect(blocked.has('3')).toBe(true)
    expect(blocked.has('5')).toBe(true)
    // não relacionados continuam disponíveis
    expect(blocked.has('4')).toBe(false)
  })

  it('parentOptions exclui o próprio serviço e descendentes, mantém "(nenhum)"', () => {
    const options = parentOptions(ROWS, '2')
    const values = options.map(o => o.value)
    expect(values).toContain('') // (nenhum)
    expect(values).not.toContain('2')
    expect(values).not.toContain('3') // descendente de 2
    expect(values).toContain('1') // ancestral continua válido como pai
    expect(values).toContain('4')
  })

  it('folha sem descendentes só bloqueia a si mesma', () => {
    const options = parentOptions(ROWS, '3')
    const values = options.map(o => o.value)
    expect(values).not.toContain('3')
    expect(values).toContain('1')
    expect(values).toContain('2')
  })
})

describe('serviceDraftFromRow / validateServiceDraft / buildServicePayload', () => {
  it('preenche o rascunho com o nome-folha (não o caminho completo)', () => {
    const draft = serviceDraftFromRow(row({ id: '3', Name: 'Suporte::Rede::Wi-Fi', ParentID: '2', Comment: 'obs' }))
    expect(draft.name).toBe('Wi-Fi')
    expect(draft.parentId).toBe('2')
    expect(draft.comment).toBe('obs')
  })

  it('rejeita nome vazio', () => {
    const draft = emptyServiceDraft()
    expect(validateServiceDraft(draft).length).toBeGreaterThan(0)
  })

  it('rejeita nome contendo "::" (hierarquia vem do campo Pai, não do nome)', () => {
    const draft = { ...emptyServiceDraft(), name: 'Suporte::Rede' }
    expect(validateServiceDraft(draft).some(e => e.includes('::'))).toBe(true)
  })

  it('aceita rascunho válido', () => {
    const draft = { ...emptyServiceDraft(), name: 'Rede', validId: '1' }
    expect(validateServiceDraft(draft)).toEqual([])
  })

  it('monta o payload: parentId vazio vira null, campos opcionais vazios somem, ValidID vira number', () => {
    const draft = { ...emptyServiceDraft(), name: '  Rede  ', parentId: '', comment: '' }
    const payload = buildServicePayload(draft)
    expect(payload.Name).toBe('Rede')
    expect(payload.ParentID).toBeNull()
    expect(payload.Comment).toBeUndefined()
    expect(payload.ValidID).toBe(1)
  })

  it('monta o payload com parentId preenchido (number)', () => {
    const draft = { ...emptyServiceDraft(), name: 'Rede', parentId: '1' }
    expect(buildServicePayload(draft).ParentID).toBe(1)
  })

  it('buildInvalidateServicePayload força ValidID=2, mantém os demais campos', () => {
    const draft = { ...emptyServiceDraft(), name: 'Rede', parentId: '1', validId: '1' }
    const payload = buildInvalidateServicePayload(draft)
    expect(payload.ValidID).toBe(2)
    expect(payload.Name).toBe('Rede')
    expect(payload.ParentID).toBe(1)
  })
})
