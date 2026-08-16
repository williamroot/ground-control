// V-R1.5 — assistente de cadastro de cliente em 3 etapas (T-R1.4).
//
// O ponto do requisito é validar POR ETAPA: hoje é um formulão de página única
// e o operador só descobre que errou o CNPJ depois de preencher branding e
// usuários. Lógica pura, testada sem Nuxt.
import { describe, expect, it } from 'vitest'
import {
  buildTenantBody,
  canAdvance,
  emptyTenantUser,
  emptyTenantWizardDraft,
  normalizeState,
  normalizeZip,
  STEP_TITLES,
  validateStep,
} from '../composables/useTenantWizard'

function fullDraft() {
  const d = emptyTenantWizardDraft()
  d.legal_name = 'Empresa Exemplo LTDA'
  d.trade_name = 'Exemplo'
  d.document = '00.000.000/0001-00'
  d.subdomain = 'exemplo'
  d.znuny_customer_id = 'EXEMPLO'
  d.display_name = 'Portal Exemplo'
  d.users = [{
    ...emptyTenantUser('admin'),
    email: 'ana@exemplo.com',
    first_name: 'Ana',
    last_name: 'Souza',
    password: 'senha-forte',
  }]
  return d
}

describe('etapa 1 — dados cadastrais', () => {
  it('não avança sem documento, e diz o porquê', () => {
    const d = fullDraft()
    d.document = ''
    expect(canAdvance(1, d)).toBe(false)
    expect(validateStep(1, d)).toContain('CNPJ/documento é obrigatório.')
  })

  it('avança com a etapa completa', () => {
    expect(canAdvance(1, fullDraft())).toBe(true)
  })

  it('recusa subdomínio com caractere que não vira hostname', () => {
    const d = fullDraft()
    d.subdomain = 'Exemplo Ltda'
    expect(validateStep(1, d)).toContain(
      'Subdomínio aceita só letras minúsculas, números e hífen.',
    )
  })

  it('endereço é opcional, mas CEP pela metade é recusado', () => {
    const d = fullDraft()
    expect(canAdvance(1, d)).toBe(true) // nenhum campo de endereço preenchido
    d.address_zip = '3011'
    expect(validateStep(1, d)).toContain('CEP deve ter 8 dígitos.')
  })

  it('e-mail de contato inválido é recusado', () => {
    const d = fullDraft()
    d.contact_email = 'sem-arroba'
    expect(validateStep(1, d)).toContain('E-mail de contato inválido.')
  })
})

describe('etapa 2 — identidade visual', () => {
  it('exige nome de exibição', () => {
    const d = fullDraft()
    d.display_name = ''
    expect(validateStep(2, d)).toContain('Nome de exibição é obrigatório.')
  })

  it('logo precisa ser https quando informado', () => {
    const d = fullDraft()
    d.logo_url = 'http://cdn.exemplo.com/logo.svg'
    expect(validateStep(2, d)).toContain('URL do logo precisa ser https://.')
    d.logo_url = 'https://cdn.exemplo.com/logo.svg'
    expect(validateStep(2, d)).toEqual([])
  })
})

describe('etapa 3 — usuários', () => {
  it('aponta o número do usuário com problema', () => {
    const d = fullDraft()
    d.users.push({ ...emptyTenantUser(), email: 'bruno@exemplo.com' })
    const errors = validateStep(3, d)
    expect(errors).toContain('Usuário 2: nome é obrigatório.')
    expect(errors).toContain('Usuário 2: senha é obrigatória.')
  })

  it('recusa dois usuários com o mesmo e-mail', () => {
    const d = fullDraft()
    d.users.push({ ...d.users[0]!, email: 'ANA@exemplo.com' })
    expect(validateStep(3, d)).toContain('E-mail repetido: ana@exemplo.com.')
  })
})

describe('normalização', () => {
  it('CEP fica só com dígitos', () => {
    expect(normalizeZip('30110-000')).toBe('30110000')
    expect(normalizeZip('30.110-000')).toBe('30110000')
  })

  it('UF vira duas letras maiúsculas', () => {
    expect(normalizeState('mg')).toBe('MG')
    expect(normalizeState('Minas')).toBe('MI')
  })
})

describe('buildTenantBody', () => {
  it('normaliza CEP e UF e apara espaços', () => {
    const d = fullDraft()
    d.address_zip = '30110-000'
    d.address_state = 'mg'
    d.legal_name = '  Empresa Exemplo LTDA  '
    const body = buildTenantBody(d)
    expect(body.address_zip).toBe('30110000')
    expect(body.address_state).toBe('MG')
    expect(body.legal_name).toBe('Empresa Exemplo LTDA')
  })

  it('campo opcional vazio some do corpo em vez de virar string vazia', () => {
    const body = buildTenantBody(fullDraft())
    expect(body.address_city).toBeUndefined()
    expect(body.contact_email).toBeUndefined()
    expect('address_city' in body).toBe(true) // a chave existe, o valor é undefined
  })

  it('mantém o contrato antigo do onboarding (branding + users)', () => {
    const body = buildTenantBody(fullDraft())
    const branding = body.branding as { display_name: string }
    const users = body.users as Array<{
      email: string
      password: string
      email_intake_enabled: boolean
    }>
    expect(branding.display_name).toBe('Portal Exemplo')
    expect(users).toHaveLength(1)
    expect(users[0]!.email).toBe('ana@exemplo.com')
    expect(users[0]!.password).toBe('senha-forte')
    expect(users[0]!.email_intake_enabled).toBe(true)
  })
})

describe('rótulos das etapas', () => {
  it('as três etapas têm título em português', () => {
    expect(STEP_TITLES[1]).toBe('Dados cadastrais')
    expect(STEP_TITLES[2]).toBe('Identidade visual')
    expect(STEP_TITLES[3]).toBe('Usuários')
  })
})
