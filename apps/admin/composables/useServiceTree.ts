// Serviços do Znuny (Spec #4, Bloco A) — lógica PURA de árvore e formulário.
// Sem Nuxt/DOM: testável isoladamente (vitest). É a parte com regra de
// verdade desta tela — a guarda anti-ciclo do seletor de "Pai".
//
// Segue a mesma convenção de `useZnunyObject.ts` (Filas/SLA, também Bloco A):
// a resposta crua do sidecar é normalizada por `extractItems`/`extractItemId`
// na página; aqui só entram registros já com `id` resolvido. `ParentID` vazio
// ("") é o sentinel de "sem pai" (serviço raiz) — mesma convenção de campo
// opcional das outras telas desta spec (ex.: `QueueDraft.Calendar`).
// O Znuny nomeia o item já com o caminho completo ("Pai::Filho"); a UI usa
// `ParentID` para montar a árvore e `leafName` para mostrar só o nível atual.

export interface ServiceRow {
  id: string
  Name: string
  ParentID: string
  Comment: string
  ValidID: string
  TypeID: string
  Criticality: string
}

export interface ServiceTreeNode {
  row: ServiceRow
  depth: number
  leafName: string
  children: ServiceTreeNode[]
}

function str(v: unknown, fallback = ''): string {
  return v === null || v === undefined ? fallback : String(v)
}

/** Normaliza um item cru de `extractItems(raw, 'Service')` para `ServiceRow`. */
export function serviceRowFromItem(item: Record<string, unknown>, id: string): ServiceRow {
  return {
    id,
    Name: str(item.Name),
    ParentID: str(item.ParentID),
    Comment: str(item.Comment),
    ValidID: str(item.ValidID, '1'),
    TypeID: str(item.TypeID),
    Criticality: str(item.Criticality),
  }
}

/** Último segmento de "Pai::Filho::Neto" — o nome exibido em cada nível da árvore. */
export function leafName(name: string): string {
  if (!name) return name
  const parts = name.split('::')
  return parts[parts.length - 1] || name
}

function groupByParent(rows: ServiceRow[]): Map<string, ServiceRow[]> {
  const byParent = new Map<string, ServiceRow[]>()
  for (const row of rows) {
    const key = row.ParentID
    if (!byParent.has(key)) byParent.set(key, [])
    byParent.get(key)!.push(row)
  }
  for (const list of byParent.values()) {
    list.sort((a, b) => leafName(a.Name).localeCompare(leafName(b.Name), 'pt-BR'))
  }
  return byParent
}

/** Monta a árvore raiz→folhas a partir da lista chapada (via ParentID). */
export function buildServiceTree(rows: ServiceRow[]): ServiceTreeNode[] {
  const byParent = groupByParent(rows)

  function build(parentKey: string, depth: number, visited: Set<string>): ServiceTreeNode[] {
    const children = byParent.get(parentKey) ?? []
    return children
      // dado corrompido (ciclo no Znuny) não deve travar a UI em loop infinito
      .filter(row => !visited.has(row.id))
      .map((row) => {
        const nextVisited = new Set(visited)
        nextVisited.add(row.id)
        return {
          row,
          depth,
          leafName: leafName(row.Name),
          children: build(row.id, depth + 1, nextVisited),
        }
      })
  }

  return build('', 0, new Set())
}

/** Achata a árvore em pré-ordem, preservando a profundidade — para renderizar linhas indentadas. */
export function flattenServiceTree(nodes: ServiceTreeNode[]): ServiceTreeNode[] {
  const out: ServiceTreeNode[] = []
  function walk(list: ServiceTreeNode[]) {
    for (const n of list) {
      out.push(n)
      walk(n.children)
    }
  }
  walk(nodes)
  return out
}

/** IDs de todos os descendentes de `rootId` (filhos, netos, ...). */
export function descendantIds(rows: ServiceRow[], rootId: string): Set<string> {
  const byParent = groupByParent(rows)
  const out = new Set<string>()
  function walk(id: string) {
    for (const child of byParent.get(id) ?? []) {
      if (out.has(child.id)) continue // guarda contra ciclo em dado corrompido
      out.add(child.id)
      walk(child.id)
    }
  }
  walk(rootId)
  return out
}

/**
 * Guarda anti-ciclo: ids que NÃO podem ser escolhidos como Pai de `editingId`
 * (o próprio serviço + todos os seus descendentes). Ao criar (`editingId` nulo)
 * nada é bloqueado.
 */
export function invalidParentIds(rows: ServiceRow[], editingId: string | null): Set<string> {
  if (!editingId) return new Set()
  return new Set([editingId, ...descendantIds(rows, editingId)])
}

export interface SelectOption { label: string, value: string }

/** Opções do select de Pai: "(nenhum)" + serviços válidos como pai, ordenados. */
export function parentOptions(rows: ServiceRow[], editingId: string | null): SelectOption[] {
  const blocked = invalidParentIds(rows, editingId)
  const options = rows
    .filter(r => !blocked.has(r.id))
    .map(r => ({ label: r.Name, value: r.id }))
    .sort((a, b) => a.label.localeCompare(b.label, 'pt-BR'))
  return [{ label: '(nenhum — serviço raiz)', value: '' }, ...options]
}

// --- Formulário --------------------------------------------------------------

export interface ServiceDraft {
  name: string
  parentId: string
  comment: string
  validId: string
  typeId: string
  criticality: string
}

export function emptyServiceDraft(): ServiceDraft {
  return { name: '', parentId: '', comment: '', validId: '1', typeId: '', criticality: '' }
}

export function serviceDraftFromRow(row: ServiceRow): ServiceDraft {
  return {
    name: leafName(row.Name),
    parentId: row.ParentID,
    comment: row.Comment,
    validId: row.ValidID,
    typeId: row.TypeID,
    criticality: row.Criticality,
  }
}

/** Validação leve (espelho do 422 do sidecar, que é a fonte de verdade). */
export function validateServiceDraft(draft: ServiceDraft): string[] {
  const errors: string[] = []
  const name = draft.name.trim()
  if (!name) errors.push('Nome é obrigatório.')
  if (name.includes('::')) errors.push('Nome não deve conter "::" — a hierarquia vem do campo Pai.')
  if (!draft.validId) errors.push('Validade é obrigatória.')
  return errors
}

export function isServiceDraftValid(draft: ServiceDraft): boolean {
  return validateServiceDraft(draft).length === 0
}

export interface ServicePayload {
  Name: string
  ParentID: number | null
  Comment?: string
  ValidID: number
  TypeID?: number
  Criticality?: string
}

export function buildServicePayload(draft: ServiceDraft): ServicePayload {
  const int = (v: string) => (v.trim() === '' ? undefined : Number(v))
  return {
    Name: draft.name.trim(),
    ParentID: draft.parentId.trim() === '' ? null : Number(draft.parentId),
    Comment: draft.comment.trim() || undefined,
    ValidID: Number(draft.validId),
    TypeID: int(draft.typeId),
    Criticality: draft.criticality.trim() || undefined,
  }
}

/** Payload de invalidação (ValidID=2) — no Znuny não existe exclusão de serviço. */
export function buildInvalidateServicePayload(draft: ServiceDraft): ServicePayload {
  return buildServicePayload({ ...draft, validId: '2' })
}
