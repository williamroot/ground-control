// Spec #4 (Bloco C) — lógica pura do cadastro de agentes e, especialmente, do
// diff de permissões (grupos/papéis) que alimenta a confirmação obrigatória
// antes de qualquer PUT de grupos — a ação mais perigosa desta spec.
import { describe, expect, it } from 'vitest'
import {
  agentDraftFromRow,
  agentFullName,
  agentValidColor,
  agentValidLabel,
  buildAgentProfilePayload,
  buildGroupsPayload,
  buildPasswordPayload,
  diffAgentGroups,
  emptyAgentDraft,
  extractAgentError,
  extractGroupsError,
  hasGroupChanges,
  isAgentProfileValid,
  isPasswordValid,
  validateAgentProfile,
  validatePassword,
  wouldRemoveSelfFromAdmin,
  describeGroupsChange,
  groupIdsFromChange,
  parseAgentList,
  parseGroupList,
  selectedGroups,
  validateGroupSelection,
  type AgentProfileDraft,
  type AgentRow,
  type GroupRow,
} from '../composables/useAgentGroups'

// Formato REAL do sidecar (admin_znuny_people.py) — o que a tela recebia em
// staging e não sabia ler (teste V01: "Nenhum agente cadastrado" com 5 agentes).
const SIDECAR_AGENTS = [
  { id: 3, login: 'william', first_name: 'William', last_name: 'Souza', email: 'w@gerti.com.br', valid: true },
  { id: 5, login: 'bruno.cardoso', first_name: 'Bruno', last_name: 'Cardoso', email: 'b@gerti.com.br', valid: true },
  { id: 9, login: 'antigo', first_name: 'Ex', last_name: 'Agente', email: 'e@gerti.com.br', valid: false },
]

describe('parseAgentList — contrato real do sidecar', () => {
  it('lê a lista pura (sem `items`) e ordena por login', () => {
    const rows = parseAgentList(SIDECAR_AGENTS)
    expect(rows?.map(r => r.login)).toEqual(['antigo', 'bruno.cardoso', 'william'])
    expect(rows?.find(r => r.login === 'william')).toEqual(SIDECAR_AGENTS[0])
  })

  it('mantém agente inválido na tela de administração (só marca)', () => {
    expect(parseAgentList(SIDECAR_AGENTS)?.find(r => r.id === 9)?.valid).toBe(false)
  })

  it('resposta que não é lista é ERRO (null), não lista vazia', () => {
    expect(parseAgentList(null)).toBeNull()
    expect(parseAgentList({ items: SIDECAR_AGENTS })).toBeNull()
    expect(parseAgentList({ detail: 'znuny_unavailable' })).toBeNull()
  })

  it('lista vazia de verdade é vazia', () => {
    expect(parseAgentList([])).toEqual([])
  })

  it('descarta item sem id inteiro ou sem login; valid só é true se for true', () => {
    const rows = parseAgentList([
      { id: 'x', login: 'a' },
      { id: 4, login: '  ' },
      { id: '7', login: 'diego', first_name: 'Diego', last_name: 'F', email: 'd@x', valid: 'yes' },
      null,
    ])
    expect(rows).toEqual([{ id: 7, login: 'diego', first_name: 'Diego', last_name: 'F', email: 'd@x', valid: false }])
  })
})

describe('parseGroupList', () => {
  it('lê [{id, name, comment, valid, rw_user_count}] e ordena por nome', () => {
    const groups = parseGroupList([
      { id: 2, name: 'users', comment: '', valid: true, rw_user_count: 5 },
      { id: 1, name: 'admin', comment: 'adm', valid: true, rw_user_count: null },
    ])
    expect(groups.map(g => g.name)).toEqual(['admin', 'users'])
    expect(groups[1]).toEqual({ id: 2, name: 'users', comment: '', valid: true, rw_user_count: 5 })
  })

  it('resposta inválida vira lista vazia', () => {
    expect(parseGroupList(null)).toEqual([])
    expect(parseGroupList({ items: [] })).toEqual([])
  })
})

const fullDraft = (over: Partial<AgentProfileDraft> = {}): AgentProfileDraft => ({
  login: 'agente1',
  first_name: 'Ana',
  last_name: 'Souza',
  email: 'ana@gerti.com.br',
  valid: 'true',
  ...over,
})

describe('validateAgentProfile — espelho do 422, NUNCA inclui senha', () => {
  it('rejeita rascunho vazio na criação', () => {
    expect(isAgentProfileValid(emptyAgentDraft(), true)).toBe(false)
  })

  it('login curto ou com espaço é inválido só na criação', () => {
    expect(validateAgentProfile(fullDraft({ login: 'ab' }), true).some(e => e.includes('Login'))).toBe(true)
    expect(validateAgentProfile(fullDraft({ login: 'jo ao' }), true).some(e => e.includes('espaços'))).toBe(true)
  })

  it('login não é validado na edição (é imutável)', () => {
    expect(validateAgentProfile(fullDraft({ login: '' }), false).some(e => e.includes('Login'))).toBe(false)
  })

  it('e-mail inválido é rejeitado', () => {
    expect(validateAgentProfile(fullDraft({ email: 'nao-eh-email' }), true).some(e => e.includes('E-mail'))).toBe(true)
  })

  it('aceita um rascunho válido completo', () => {
    expect(isAgentProfileValid(fullDraft(), true)).toBe(true)
  })
})

describe('buildAgentProfilePayload — corpo do POST/PUT do sidecar', () => {
  it('POST: { login, first_name, last_name, email, valid } com valid booleano', () => {
    const payload = buildAgentProfilePayload(fullDraft({ login: '  agente1  ', first_name: ' Ana ' }), true)
    expect(payload).toEqual({
      login: 'agente1',
      first_name: 'Ana',
      last_name: 'Souza',
      email: 'ana@gerti.com.br',
      valid: true,
    })
  })

  it('PUT: sem login (AgentUpdate não tem o campo)', () => {
    const payload = buildAgentProfilePayload(fullDraft({ valid: 'false' }), false)
    expect(payload).toEqual({ first_name: 'Ana', last_name: 'Souza', email: 'ana@gerti.com.br', valid: false })
    expect('login' in payload).toBe(false)
  })

  it('payload nunca tem chave de senha', () => {
    const payload = buildAgentProfilePayload(fullDraft(), true) as unknown as Record<string, unknown>
    for (const k of ['UserPw', 'NewPassword', 'password', 'new_password']) expect(k in payload).toBe(false)
  })
})

describe('agentDraftFromRow / agentFullName / rótulos', () => {
  const row: AgentRow = { id: 1, login: 'agente1', first_name: 'Ana', last_name: 'Souza', email: 'ana@gerti.com.br', valid: false }

  it('preenche o rascunho a partir do agente carregado', () => {
    expect(agentDraftFromRow(row)).toEqual({
      login: 'agente1', first_name: 'Ana', last_name: 'Souza', email: 'ana@gerti.com.br', valid: 'false',
    })
  })

  it('monta nome completo', () => {
    expect(agentFullName(row)).toBe('Ana Souza')
  })

  it('rótulo/cor de validade (booleano do sidecar)', () => {
    expect(agentValidLabel(false)).toBe('inválido')
    expect(agentValidColor(false)).toBe('error')
    expect(agentValidLabel(true)).toBe('válido')
    expect(agentValidColor(true)).toBe('success')
  })
})

describe('senha — ação separada e explícita', () => {
  it('exige tamanho mínimo e confirmação igual', () => {
    expect(isPasswordValid('curta', 'curta')).toBe(false)
    expect(validatePassword('senhaseguraverde', 'outradiferentee').some(e => e.includes('coincidem'))).toBe(true)
  })

  it('senha válida e confirmada passa', () => {
    expect(isPasswordValid('senha-super-segura', 'senha-super-segura')).toBe(true)
  })

  it('payload de senha só tem new_password', () => {
    expect(buildPasswordPayload('senha-super-segura')).toEqual({ new_password: 'senha-super-segura' })
  })
})

describe('extractAgentError', () => {
  it('usa a mensagem do sidecar quando presente', () => {
    expect(extractAgentError({ statusCode: 422, data: { detail: 'login já existe' } })).toBe('login já existe')
  })

  it('traduz o código de indisponibilidade', () => {
    expect(extractAgentError({ statusCode: 503, data: { detail: 'znuny_unavailable' } })).toContain('indisponível')
  })

  it('cai no genérico sem detalhe', () => {
    expect(extractAgentError(new Error('boom'))).toContain('Falha ao salvar')
  })
})

const groups: GroupRow[] = [
  { id: 1, name: 'admin' },
  { id: 2, name: 'users' },
  { id: 3, name: 'faturamento' },
]

describe('diffAgentGroups — confirmação quando os grupos atuais são conhecidos', () => {
  it('detecta ganhos e perdas corretamente', () => {
    const diff = diffAgentGroups([1, 2], [2, 3], groups)
    expect(diff.lost.map(g => g.name)).toEqual(['admin'])
    expect(diff.gained.map(g => g.name)).toEqual(['faturamento'])
    expect(diff.unchanged.map(g => g.name)).toEqual(['users'])
  })

  it('sem mudança nenhuma: gained e lost vazios', () => {
    const diff = diffAgentGroups([1, 2], [2, 1], groups)
    expect(hasGroupChanges(diff)).toBe(false)
  })

  it('hasGroupChanges é true quando há ganho ou perda', () => {
    expect(hasGroupChanges(diffAgentGroups([1], [1, 2], groups))).toBe(true)
  })

  it('grupo desconhecido (fora da lista de apoio) ainda aparece pelo id', () => {
    expect(diffAgentGroups([], [99], groups).gained[0]).toEqual({ id: 99, name: '#99' })
  })

  it('ids número e string são equivalentes', () => {
    const diff = diffAgentGroups(['1', 2], [1, '2'], groups)
    expect(hasGroupChanges(diff)).toBe(false)
  })

  it('ordena por nome (pt-BR)', () => {
    expect(selectedGroups([2, 3, 1], groups).map(g => g.name)).toEqual(['admin', 'faturamento', 'users'])
  })
})

describe('validateGroupSelection — o PUT substitui tudo', () => {
  it('seleção vazia é recusada (tiraria todo acesso)', () => {
    expect(validateGroupSelection([])).toHaveLength(1)
    expect(validateGroupSelection(['x'])).toHaveLength(1)
  })

  it('ao menos um grupo passa', () => {
    expect(validateGroupSelection([2])).toEqual([])
  })
})

describe('wouldRemoveSelfFromAdmin — guarda anti-lockout', () => {
  it('conhecido: true quando é o próprio agente perdendo o admin', () => {
    expect(wouldRemoveSelfFromAdmin(true, [1, 2], [2], groups)).toBe(true)
  })

  it('conhecido: false quando ele já não era admin', () => {
    expect(wouldRemoveSelfFromAdmin(true, [2], [2, 3], groups)).toBe(false)
  })

  it('desconhecido: conservador — basta o admin estar desmarcado', () => {
    expect(wouldRemoveSelfFromAdmin(true, null, [2], groups)).toBe(true)
    expect(wouldRemoveSelfFromAdmin(true, null, [1, 2], groups)).toBe(false)
  })

  it('false quando não é o próprio agente', () => {
    expect(wouldRemoveSelfFromAdmin(false, null, [2], groups)).toBe(false)
  })

  it('false quando o Znuny não tem grupo admin na lista', () => {
    expect(wouldRemoveSelfFromAdmin(true, null, [2], [{ id: 2, name: 'users' }])).toBe(false)
  })
})

describe('buildGroupsPayload — corpo do PUT /agents/{id}/groups', () => {
  it('{ group_ids } inteiros, sem repetição, ordenados; sem permissions', () => {
    expect(buildGroupsPayload([3, '1', 3, 'x'])).toEqual({ group_ids: [1, 3] })
  })
})

describe('resposta do PUT de grupos', () => {
  const change = { agent_id: 5, before: [{ id: 1, name: 'admin' }], after: [{ id: 2, name: 'users' }, { id: 3, name: 'faturamento' }] }

  it('o `after` vira o estado conhecido', () => {
    expect(groupIdsFromChange(change)).toEqual([2, 3])
    expect(groupIdsFromChange(null)).toBeNull()
  })

  it('descreve antes e depois', () => {
    expect(describeGroupsChange(change)).toBe('Antes: admin. Agora: users, faturamento.')
    expect(describeGroupsChange({ before: [], after: [] })).toBe('Antes: nenhum grupo. Agora: nenhum grupo.')
  })
})

describe('extractGroupsError — trata o 422 de anti-lockout em vez de mostrar cru', () => {
  it('explica o anti-lockout quando é o cenário detectado, mesmo sem detail', () => {
    expect(extractGroupsError({ statusCode: 422, data: {} }, true)).toContain('não pode remover a si mesmo do grupo administrador')
  })

  it('usa a mensagem do sidecar quando não é o cenário de lockout', () => {
    expect(extractGroupsError({ statusCode: 422, data: { detail: 'grupo inexistente' } }, false)).toBe('grupo inexistente')
  })

  it('cai no genérico sem detalhe e sem lockout', () => {
    expect(extractGroupsError(new Error('boom'), false)).toContain('Falha ao salvar')
  })
})
