// V-R2.6 / V-R2.7 — cadastro único da pessoa do cliente (T-R2.5) e o guard dos
// proxies que interpolam o login no path do sidecar.
//
// Dois riscos concretos cobertos aqui:
//   1. um payload de EDIÇÃO carregando senha — a op Perl rejeita qualquer chave
//      com cara de senha, então isso viraria 4xx em produção;
//   2. um login com `../` subindo um nível no path do sidecar, com o cookie de
//      agente junto.
import { describe, expect, it } from 'vitest'
import {
  buildCreatePayload,
  buildUpdatePayload,
  CADASTRO_UNICO_HINT,
  confirmDeactivateMatches,
  draftFromUser,
  emptyUserDraft,
  userStatusLabel,
  validateUserDraft,
  type TenantUser,
} from '../composables/useTenantUsers'
import { isCustomerLogin, isTenantId } from '../server/utils/znuny'

function draft() {
  return {
    ...emptyUserDraft(),
    email: 'ana@acme.example',
    first_name: 'Ana',
    last_name: 'Souza',
    password: 'senha-forte',
    phone: '+553133330000',
    extension: '204',
  }
}

describe('validateUserDraft', () => {
  it('recusa e-mail sem arroba', () => {
    expect(validateUserDraft({ email: 'sem-arroba' })).toContain('E-mail inválido.')
  })

  it('exige nome, sobrenome e senha na criação', () => {
    const errors = validateUserDraft({ email: 'ana@acme.example' })
    expect(errors).toContain('Nome é obrigatório.')
    expect(errors).toContain('Sobrenome é obrigatório.')
    expect(errors).toContain('Senha é obrigatória.')
  })

  it('na edição não exige senha', () => {
    const errors = validateUserDraft({ email: 'ana@acme.example' }, { isEdit: true })
    expect(errors).toEqual([])
  })

  it('cadastro completo passa', () => {
    expect(validateUserDraft(draft())).toEqual([])
  })
})

describe('payloads', () => {
  it('a criação leva senha', () => {
    expect(buildCreatePayload(draft()).password).toBe('senha-forte')
  })

  it('a EDIÇÃO nunca carrega senha', () => {
    const payload = buildUpdatePayload(draft())
    expect('password' in payload).toBe(false)
    expect(Object.keys(payload).some(k => /pw|password|senha/i.test(k))).toBe(false)
  })

  it('ramal vazio vira null na edição — é como se limpa o campo', () => {
    const d = { ...draft(), extension: '   ' }
    expect(buildUpdatePayload(d).extension).toBeNull()
  })

  it('campo opcional vazio some do corpo de criação', () => {
    const d = { ...draft(), phone: '', extension: '' }
    const payload = buildCreatePayload(d)
    expect(payload.phone).toBeUndefined()
    expect(payload.extension).toBeUndefined()
  })
})

describe('confirmDeactivateMatches', () => {
  it('aceita o e-mail exato, ignorando caixa e espaços', () => {
    expect(confirmDeactivateMatches('ana@acme.example', 'ana@acme.example')).toBe(true)
    expect(confirmDeactivateMatches('  ANA@Acme.Example ', 'ana@acme.example')).toBe(true)
  })

  it('recusa qualquer outro texto', () => {
    expect(confirmDeactivateMatches('ana', 'ana@acme.example')).toBe(false)
    expect(confirmDeactivateMatches('', 'ana@acme.example')).toBe(false)
    expect(confirmDeactivateMatches('sim', 'ana@acme.example')).toBe(false)
  })
})

describe('estado da pessoa na tabela', () => {
  const base: TenantUser = {
    customer_login: 'ana@acme.example',
    first_name: 'Ana',
    last_name: 'Souza',
    email: 'ana@acme.example',
    phone: '',
    mobile: '',
    extension: null,
    active: true,
    role: 'helpdesk',
    email_intake_enabled: true,
    has_portal_access: true,
  }

  it('distingue inativo, sem portal e ativo', () => {
    expect(userStatusLabel({ ...base, active: false })).toBe('Inativo')
    expect(userStatusLabel({ ...base, has_portal_access: false, role: null }))
      .toBe('Sem acesso ao portal')
    expect(userStatusLabel(base)).toBe('Ativo')
  })

  it('draftFromUser cai em helpdesk quando a pessoa não tem papel', () => {
    const d = draftFromUser({ ...base, role: null, has_portal_access: false })
    expect(d.role).toBe('helpdesk')
    expect(d.password).toBe('')
  })
})

describe('o texto do diferencial fica na tela', () => {
  it('diz que portal e e-mail são o mesmo cadastro', () => {
    expect(CADASTRO_UNICO_HINT).toContain('portal')
    expect(CADASTRO_UNICO_HINT).toContain('e-mail')
    expect(CADASTRO_UNICO_HINT).toContain('mesmo cadastro')
  })
})

describe('guards dos proxies (V-R2.7)', () => {
  it('id de tenant só passa se for UUID', () => {
    expect(isTenantId('11111111-2222-3333-4444-555555555555')).toBe(true)
    expect(isTenantId('nao-e-uuid')).toBe(false)
    expect(isTenantId('../../v1/admin/tenants')).toBe(false)
    expect(isTenantId('')).toBe(false)
    expect(isTenantId(undefined)).toBe(false)
  })

  it('login com path traversal é recusado antes de chamar o sidecar', () => {
    expect(isCustomerLogin('ana@acme.example')).toBe(true)
    expect(isCustomerLogin('../ana@acme.example')).toBe(false)
    expect(isCustomerLogin('ana/../../admin@acme.example')).toBe(false)
    expect(isCustomerLogin('ana%2f@acme.example')).toBe(false)
    expect(isCustomerLogin('ana acme@example.com')).toBe(false)
    expect(isCustomerLogin('ana\\@acme.example')).toBe(false)
  })

  it('login sem arroba não é login de cliente', () => {
    expect(isCustomerLogin('ana')).toBe(false)
    expect(isCustomerLogin('')).toBe(false)
    expect(isCustomerLogin(undefined)).toBe(false)
  })

  it('recusa login absurdamente longo', () => {
    expect(isCustomerLogin(`${'a'.repeat(250)}@acme.example`)).toBe(false)
  })
})
