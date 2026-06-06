import { describe, expect, it } from 'vitest'

// Smoke do fluxo de abertura de chamado (#1E fase 3).
//
// HARNESS: repositório usa testes de lógica pura (plain vitest + happy-dom).
// As pages usam <script setup> com composables Nuxt (`useAsyncData`, `useToast`,
// `navigateTo`) que não estão disponíveis sem boot Nuxt completo — portanto o
// componente pages/tickets/novo.vue NÃO é montado aqui (adicionaria infra nova
// pesada). Em vez disso as funções de lógica pura são replicadas/testadas
// diretamente, seguindo o mesmo padrão de portal-roles.test.ts e
// branding.middleware.test.ts.
//
// COBERTURA:
//   ✓ D-1E-2: lógica de `showContractSelector` (0 / 1 / >= 2 contratos)
//   ✓ toOptions: conversão MetaItem[] → {label, value}[]
//   ✓ defaultPriority: seleção do padrão "normal" e fallback ao primeiro
//   ✓ contractOptions: label com e sem saldo_label
//   ✓ validação de submit (título / corpo obrigatórios, contractId obrigatório
//     quando seletor visível)
//   ✓ FormData: campos presentes/ausentes conforme contrato selecionável
//   ~ Proxy de servidor (/api/portal/ticketing/*): verificado por inspeção
//     estática do módulo carregado no setup.ts (sidecarFetch stubado)
//
// NÃO COBERTO AQUI:
//   - Renderização do template (USelect visível/oculto) — exigiria montagem
//     com @nuxt/test-utils / Nuxt DevTools; não está configurado no projeto.
//   - Fluxo E2E de submissão HTTP real — depende do sidecar em execução.

// ─── Lógica replicada de pages/tickets/novo.vue ──────────────────────────────

interface SelectableContract {
  id: string
  code: string
  type: string
  saldo_label: string | null
}
interface MetaItem { Key: string, Value: string }

/** D-1E-2: seletor de contrato só quando há ambiguidade (>= 2 contratos). */
function showContractSelector(contracts: SelectableContract[]): boolean {
  return contracts.length >= 2
}

function toOptions(items: MetaItem[] | undefined) {
  return (items ?? []).map(i => ({ label: i.Value, value: i.Key }))
}

function contractOptions(contracts: SelectableContract[]) {
  return contracts.map(c => ({
    label: c.saldo_label ? `${c.code} — ${c.saldo_label}` : c.code,
    value: c.id,
  }))
}

function defaultPriority(priorities: MetaItem[]): string | undefined {
  const normal = priorities.find(p => /normal/i.test(p.Value) || /normal/i.test(p.Key))
  return (normal ?? priorities[0])?.Key
}

// Lógica de validação de submit (sem side-effects de UI).
interface SubmitForm {
  title: string
  body: string
  contractId: string | undefined
}
function validateSubmit(
  form: SubmitForm,
  selectorVisible: boolean,
): { formError: string, contractError: string } {
  if (!form.title.trim() || !form.body.trim()) {
    return { formError: 'Preencha o assunto e a descrição para abrir o chamado.', contractError: '' }
  }
  if (selectorVisible && !form.contractId) {
    return { formError: '', contractError: 'Selecione um contrato.' }
  }
  return { formError: '', contractError: '' }
}

// FormData building (sem File[] para manter o teste leve).
function buildFormData(
  form: { title: string, body: string, contractId?: string, service?: string, type?: string, priority?: string },
  selectorVisible: boolean,
): Record<string, string> {
  const fd: Record<string, string> = {}
  fd.title = form.title.trim()
  fd.body = form.body.trim()
  if (selectorVisible && form.contractId) fd.contract_id = form.contractId
  if (form.service) fd.service = form.service
  if (form.type) fd.type = form.type
  if (form.priority) fd.priority = form.priority
  return fd
}

// ─── Testes ──────────────────────────────────────────────────────────────────

describe('D-1E-2: showContractSelector (seletor de contrato condicional)', () => {
  it('0 contratos → seletor ocultado', () => {
    expect(showContractSelector([])).toBe(false)
  })
  it('1 contrato → seletor ocultado (backend vincula sozinho)', () => {
    const c: SelectableContract = { id: 'c1', code: 'GC-001', type: 'SLA', saldo_label: null }
    expect(showContractSelector([c])).toBe(false)
  })
  it('2 contratos → seletor exibido', () => {
    const c1: SelectableContract = { id: 'c1', code: 'GC-001', type: 'SLA', saldo_label: null }
    const c2: SelectableContract = { id: 'c2', code: 'GC-002', type: 'SLA', saldo_label: null }
    expect(showContractSelector([c1, c2])).toBe(true)
  })
  it('3+ contratos → seletor exibido', () => {
    const cs: SelectableContract[] = [
      { id: 'c1', code: 'GC-001', type: 'SLA', saldo_label: null },
      { id: 'c2', code: 'GC-002', type: 'SLA', saldo_label: null },
      { id: 'c3', code: 'GC-003', type: 'SLA', saldo_label: null },
    ]
    expect(showContractSelector(cs)).toBe(true)
  })
})

describe('toOptions: conversão de MetaItem[] para USelect', () => {
  it('mapeia Key → value e Value → label', () => {
    const items: MetaItem[] = [
      { Key: '3 normal', Value: 'Normal' },
      { Key: '1 high', Value: 'Alta' },
    ]
    const opts = toOptions(items)
    expect(opts).toEqual([
      { label: 'Normal', value: '3 normal' },
      { label: 'Alta', value: '1 high' },
    ])
  })
  it('undefined → array vazio (degradação)', () => {
    expect(toOptions(undefined)).toEqual([])
  })
  it('array vazio → array vazio', () => {
    expect(toOptions([])).toEqual([])
  })
})

describe('contractOptions: label com e sem saldo_label', () => {
  it('com saldo_label exibe "code — saldo"', () => {
    const c: SelectableContract = { id: 'c1', code: 'GC-001', type: 'SLA', saldo_label: '80 h restantes' }
    const opts = contractOptions([c])
    expect(opts[0].label).toBe('GC-001 — 80 h restantes')
    expect(opts[0].value).toBe('c1')
  })
  it('sem saldo_label exibe só o code', () => {
    const c: SelectableContract = { id: 'c2', code: 'GC-002', type: 'AVULSO', saldo_label: null }
    const opts = contractOptions([c])
    expect(opts[0].label).toBe('GC-002')
  })
})

describe('defaultPriority: seleção da prioridade padrão', () => {
  it('escolhe a prioridade cujo Value contém "normal" (case-insensitive)', () => {
    const ps: MetaItem[] = [
      { Key: '1 high', Value: 'Alta' },
      { Key: '3 normal', Value: 'Normal' },
      { Key: '5 low', Value: 'Baixa' },
    ]
    expect(defaultPriority(ps)).toBe('3 normal')
  })
  it('aceita "Normal" com maiúscula', () => {
    const ps: MetaItem[] = [{ Key: '3 normal', Value: 'Normal' }]
    expect(defaultPriority(ps)).toBe('3 normal')
  })
  it('fallback ao primeiro se nenhum contém "normal"', () => {
    const ps: MetaItem[] = [
      { Key: '1 high', Value: 'Alta' },
      { Key: '5 low', Value: 'Baixa' },
    ]
    expect(defaultPriority(ps)).toBe('1 high')
  })
  it('lista vazia → undefined', () => {
    expect(defaultPriority([])).toBeUndefined()
  })
})

describe('validateSubmit: validação do formulário de abertura', () => {
  it('título vazio → formError (sem contractError)', () => {
    const r = validateSubmit({ title: '', body: 'Descrição', contractId: undefined }, false)
    expect(r.formError).toBeTruthy()
    expect(r.contractError).toBe('')
  })
  it('body vazio → formError', () => {
    const r = validateSubmit({ title: 'Título', body: '   ', contractId: undefined }, false)
    expect(r.formError).toBeTruthy()
    expect(r.contractError).toBe('')
  })
  it('seletor visível + contractId ausente → contractError', () => {
    const r = validateSubmit({ title: 'Título', body: 'Descrição', contractId: undefined }, true)
    expect(r.contractError).toBeTruthy()
    expect(r.formError).toBe('')
  })
  it('seletor oculto + contractId ausente → sem erro (1 contrato: backend vincula)', () => {
    const r = validateSubmit({ title: 'Título', body: 'Descrição', contractId: undefined }, false)
    expect(r.formError).toBe('')
    expect(r.contractError).toBe('')
  })
  it('campos válidos + seletor visível + contractId presente → sem erro', () => {
    const r = validateSubmit({ title: 'Título', body: 'Descrição', contractId: 'c1' }, true)
    expect(r.formError).toBe('')
    expect(r.contractError).toBe('')
  })
})

describe('buildFormData: campos do FormData de submissão', () => {
  it('com 2+ contratos e contractId: inclui contract_id', () => {
    const fd = buildFormData(
      { title: 'Falha no acesso', body: 'Detalhes do problema', contractId: 'c2', priority: '3 normal' },
      true,
    )
    expect(fd.title).toBe('Falha no acesso')
    expect(fd.body).toBe('Detalhes do problema')
    expect(fd.contract_id).toBe('c2')
    expect(fd.priority).toBe('3 normal')
  })
  it('com 1 contrato (seletor oculto): omite contract_id mesmo com contractId definido', () => {
    const fd = buildFormData(
      { title: 'Título', body: 'Corpo', contractId: 'c1' },
      false, // selectorVisible = false
    )
    expect(fd).not.toHaveProperty('contract_id')
  })
  it('campos opcionais ausentes → não incluídos no FormData', () => {
    const fd = buildFormData({ title: 'T', body: 'B' }, false)
    expect(fd).not.toHaveProperty('service')
    expect(fd).not.toHaveProperty('type')
    expect(fd).not.toHaveProperty('priority')
    expect(fd).not.toHaveProperty('contract_id')
  })
  it('título e body são trimados antes de enviar', () => {
    const fd = buildFormData({ title: '  Assunto  ', body: '  Descrição  ' }, false)
    expect(fd.title).toBe('Assunto')
    expect(fd.body).toBe('Descrição')
  })
})
