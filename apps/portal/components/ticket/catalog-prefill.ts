// Spec #3 · V2 — pré-preenchimento de /tickets/novo a partir de
// ?servico=<id> do catálogo de serviços.
//
// DIVERGÊNCIA DO CONTRATO (documentada, não improvisada — regra do documento
// da spec): o contrato pede pré-preencher "assunto, fila, serviço e
// prioridade". O endpoint de criação de chamado (`POST /v1/tickets`, ver
// `routers/tickets.py`) e o form-meta (`GET /v1/ticketing/form-meta`) só
// aceitam/expõem `service`/`type`/`priority` — não existe campo de fila
// (`queue`) em nenhum dos dois hoje. Não há como o portal enviar uma fila ao
// abrir o chamado; inventar um campo "editável" que não é submetido seria
// enganoso. `znuny_queue` do item, quando presente, é exibido como texto
// informativo (ver alerta em tickets/novo.vue) — nunca como campo de form.

export interface MetaItem { Key: string, Value: string }

export interface CatalogItemForPrefill {
  name: string
  znuny_service: string | null
  default_priority: string | null
}

/** Lê `route.query.servico` (string | string[] | undefined) → id ('' = ausente). */
export function resolveServicoId(raw: string | string[] | undefined): string {
  const v = Array.isArray(raw) ? raw[0] : raw
  return v ? String(v) : ''
}

/**
 * Acha a `Key` do meta (services/priorities do Znuny) cujo `Key` OU `Value`
 * bate (case-insensitive) com o valor salvo no item de catálogo. `undefined`
 * quando não há valor desejado ou nenhuma opção corresponde (o `<USelect>`
 * fica sem seleção — nunca quebra por um valor desconhecido).
 */
export function matchMetaKey(items: MetaItem[], wanted: string | null | undefined): string | undefined {
  const w = (wanted ?? '').trim().toLowerCase()
  if (!w) return undefined
  const hit = items.find(i => i.Key.toLowerCase() === w || i.Value.toLowerCase() === w)
  return hit?.Key
}

/**
 * Deriva os valores iniciais de assunto/serviço/prioridade a partir do item
 * de catálogo resolvido (já é `null` se o id não existir/estiver inativo —
 * o proxy devolve 404→null nesse caso, então esta função nem entra em jogo).
 * Todos os campos retornados continuam editáveis no form normalmente.
 */
export function prefillFromCatalogItem(
  item: CatalogItemForPrefill | null,
  services: MetaItem[],
  priorities: MetaItem[],
): { title: string, service: string | undefined, priority: string | undefined } {
  if (!item) return { title: '', service: undefined, priority: undefined }
  return {
    title: item.name,
    service: matchMetaKey(services, item.znuny_service),
    priority: matchMetaKey(priorities, item.default_priority),
  }
}
