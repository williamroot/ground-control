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
  type AgentRow,
  type GroupRow,
} from '../composables/useAgentGroups'

describe('validateAgentProfile — espelho do 422, NUNCA inclui senha', () => {
  it('rejeita rascunho vazio na criação', () => {
    const draft = emptyAgentDraft()
    expect(isAgentProfileValid(draft, true)).toBe(false)
  })

  it('login curto ou com espaço é inválido só na criação', () => {
    const draft = { ...emptyAgentDraft(), UserLogin: 'ab', UserFirstname: 'A', UserLastname: 'B', UserEmail: 'a@b.com' }
    expect(validateAgentProfile(draft, true).some(e => e.includes('Login'))).toBe(true)
    const draft2 = { ...draft, UserLogin: 'jo ao' }
    expect(validateAgentProfile(draft2, true).some(e => e.includes('espaços'))).toBe(true)
  })

  it('login não é validado na edição (é imutável)', () => {
    const draft = { ...emptyAgentDraft(), UserLogin: '', UserFirstname: 'A', UserLastname: 'B', UserEmail: 'a@b.com' }
    expect(validateAgentProfile(draft, false).some(e => e.includes('Login'))).toBe(false)
  })

  it('e-mail inválido é rejeitado', () => {
    const draft = { ...emptyAgentDraft(), UserLogin: 'agente1', UserFirstname: 'A', UserLastname: 'B', UserEmail: 'nao-eh-email' }
    expect(validateAgentProfile(draft, true).some(e => e.includes('E-mail'))).toBe(true)
  })

  it('aceita um rascunho válido completo', () => {
    const draft = { UserLogin: 'agente1', UserFirstname: 'Ana', UserLastname: 'Souza', UserEmail: 'ana@gerti.com.br', ValidID: '1' }
    expect(isAgentProfileValid(draft, true)).toBe(true)
  })
})

describe('buildAgentProfilePayload — nunca carrega senha', () => {
  it('inclui UserLogin só na criação', () => {
    const draft = { UserLogin: '  agente1  ', UserFirstname: ' Ana ', UserLastname: 'Souza', UserEmail: 'ana@gerti.com.br', ValidID: '1' }
    const created = buildAgentProfilePayload(draft, true)
    expect(created.UserLogin).toBe('agente1')
    const updated = buildAgentProfilePayload(draft, false)
    expect(updated.UserLogin).toBeUndefined()
    expect(updated.UserFirstname).toBe('Ana')
  })

  it('payload nunca tem chave de senha', () => {
    const draft = { UserLogin: 'agente1', UserFirstname: 'Ana', UserLastname: 'Souza', UserEmail: 'ana@gerti.com.br', ValidID: '1' }
    const payload = buildAgentProfilePayload(draft, true) as Record<string, unknown>
    expect('UserPw' in payload).toBe(false)
    expect('NewPassword' in payload).toBe(false)
    expect('password' in payload).toBe(false)
  })
})

describe('agentDraftFromRow / agentFullName / rótulos', () => {
  const row: AgentRow = { UserID: 1, UserLogin: 'agente1', UserFirstname: 'Ana', UserLastname: 'Souza', UserEmail: 'ana@gerti.com.br', ValidID: 2 }

  it('preenche o rascunho a partir do agente carregado', () => {
    const draft = agentDraftFromRow(row)
    expect(draft.UserLogin).toBe('agente1')
    expect(draft.ValidID).toBe('2')
  })

  it('monta nome completo', () => {
    expect(agentFullName(row)).toBe('Ana Souza')
  })

  it('rótulo/cor de validade', () => {
    expect(agentValidLabel(row.ValidID)).toBe('inválido')
    expect(agentValidColor(row.ValidID)).toBe('error')
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

  it('cai no genérico sem detalhe', () => {
    expect(extractAgentError(new Error('boom'))).toContain('Falha ao salvar')
  })
})

describe('diffAgentGroups — o coração da tela de confirmação', () => {
  const groups: GroupRow[] = [
    { GroupID: 1, Name: 'admin' },
    { GroupID: 2, Name: 'users' },
    { GroupID: 3, Name: 'faturamento' },
  ]

  it('detecta ganhos e perdas corretamente', () => {
    const diff = diffAgentGroups([1, 2], [2, 3], groups)
    expect(diff.lost.map(g => g.Name)).toEqual(['admin'])
    expect(diff.gained.map(g => g.Name)).toEqual(['faturamento'])
    expect(diff.unchanged.map(g => g.Name)).toEqual(['users'])
  })

  it('sem mudança nenhuma: gained e lost vazios', () => {
    const diff = diffAgentGroups([1, 2], [2, 1], groups)
    expect(diff.gained).toEqual([])
    expect(diff.lost).toEqual([])
    expect(hasGroupChanges(diff)).toBe(false)
  })

  it('hasGroupChanges é true quando há ganho ou perda', () => {
    const diff = diffAgentGroups([1], [1, 2], groups)
    expect(hasGroupChanges(diff)).toBe(true)
  })

  it('grupo desconhecido (fora da lista de apoio) ainda aparece no diff pelo id', () => {
    const diff = diffAgentGroups([], [99], groups)
    expect(diff.gained[0]?.GroupID).toBe('99')
  })

  it('ids número e string são equivalentes (normalização)', () => {
    const diff = diffAgentGroups(['1', 2], [1, '2'], groups)
    expect(diff.gained).toEqual([])
    expect(diff.lost).toEqual([])
  })

  it('ordena por nome (pt-BR)', () => {
    const diff = diffAgentGroups([], [1, 2, 3], groups)
    expect(diff.gained.map(g => g.Name)).toEqual(['admin', 'faturamento', 'users'])
  })
})

describe('wouldRemoveSelfFromAdmin — guarda anti-lockout', () => {
  const groups: GroupRow[] = [{ GroupID: 1, Name: 'admin' }, { GroupID: 2, Name: 'users' }]

  it('true quando é o próprio agente perdendo o grupo admin', () => {
    const diff = diffAgentGroups([1, 2], [2], groups)
    expect(wouldRemoveSelfFromAdmin(true, diff)).toBe(true)
  })

  it('false quando não é o próprio agente (mesmo perdendo admin)', () => {
    const diff = diffAgentGroups([1, 2], [2], groups)
    expect(wouldRemoveSelfFromAdmin(false, diff)).toBe(false)
  })

  it('false quando é o próprio agente mas não perde admin', () => {
    const diff = diffAgentGroups([1, 2], [1, 2, 2], groups)
    expect(wouldRemoveSelfFromAdmin(true, diff)).toBe(false)
  })

  it('false quando perde outro grupo que não admin', () => {
    const diff = diffAgentGroups([1, 2], [1], groups)
    expect(wouldRemoveSelfFromAdmin(true, diff)).toBe(false)
  })
})

describe('buildGroupsPayload', () => {
  it('normaliza ids para string', () => {
    expect(buildGroupsPayload([1, '2', 3])).toEqual({ GroupIDs: ['1', '2', '3'] })
  })
})

describe('extractGroupsError — trata o 422 de anti-lockout em vez de mostrar cru', () => {
  it('explica o anti-lockout quando é o cenário detectado, mesmo sem detail', () => {
    const err = { statusCode: 422, data: {} }
    expect(extractGroupsError(err, true)).toContain('não pode remover a si mesmo do grupo administrador')
  })

  it('usa a mensagem do sidecar quando não é o cenário de lockout', () => {
    const err = { statusCode: 422, data: { detail: 'grupo inexistente' } }
    expect(extractGroupsError(err, false)).toBe('grupo inexistente')
  })

  it('cai no genérico sem detalhe e sem lockout', () => {
    expect(extractGroupsError(new Error('boom'), false)).toContain('Falha ao salvar')
  })
})
