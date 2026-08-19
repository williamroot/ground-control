// V-R9.x — lógica pura da tela de e-mail (T-R9.7).
//
// Dois riscos concretos:
//   1. a senha da caixa aparecer onde não deve, ou o "salvar sem trocar senha"
//      mandar string vazia e apagar a senha guardada;
//   2. o regex do domínio casar mais do que devia — `@cliente.com.br` sem
//      escapar o ponto casaria `@clienteXcomYbr`, e e-mail de um domínio
//      parecido cairia como sendo do cliente errado.
import { describe, expect, it } from 'vitest'
import {
  buildDomainRulePayload,
  buildMailAccountPayload,
  customerOfFilter,
  domainOfFilter,
  draftFromAccount,
  emptyMailAccountDraft,
  OUTBOUND_WARNING,
  passwordPlaceholder,
  validateDomainRule,
  validateMailAccount,
  type MailAccount,
  type PostMasterFilter,
} from '../composables/useMailConfig'
import { isFilterName } from '../server/utils/znuny'

const account: MailAccount = {
  id: 7,
  login: 'suporte@gerti.com.br',
  host: 'imap.gerti.com.br',
  type: 'IMAPS',
  valid: true,
  trusted: false,
  dispatching_by: 'Queue',
  queue_id: 6,
  queue_name: 'Suporte::N1',
  comment: '',
  imap_folder: 'INBOX',
  has_password: true,
}

describe('conta de recebimento', () => {
  it('exige fila quando a entrega é por fila', () => {
    const d = { ...emptyMailAccountDraft(), login: 'a@b.com', host: 'imap.b.com', password: 'x' }
    expect(validateMailAccount(d)).toContain(
      'Escolha a fila que vai receber as mensagens desta caixa.',
    )
    expect(validateMailAccount({ ...d, queue_id: 6 })).toEqual([])
  })

  it('exige senha ao criar, mas não ao editar', () => {
    const novo = { ...emptyMailAccountDraft(), login: 'a@b.com', host: 'imap.b.com', queue_id: 6 }
    expect(validateMailAccount(novo)).toContain(
      'Senha é obrigatória ao cadastrar uma caixa nova.',
    )
    expect(validateMailAccount({ ...novo, id: 7 })).toEqual([])
  })

  it('o rascunho de edição NUNCA vem com senha preenchida', () => {
    expect(draftFromAccount(account).password).toBe('')
  })

  it('salvar sem digitar senha não manda o campo — não apaga a guardada', () => {
    const payload = buildMailAccountPayload(draftFromAccount(account))
    expect('password' in payload).toBe(false)
    expect(payload.queue_id).toBe(6)
  })

  it('salvar COM senha digitada manda o campo', () => {
    const d = { ...draftFromAccount(account), password: 'nova' }
    expect(buildMailAccountPayload(d).password).toBe('nova')
  })

  it('senha em branco (só espaços) conta como "não mexer"', () => {
    const d = { ...draftFromAccount(account), password: '   ' }
    expect('password' in buildMailAccountPayload(d)).toBe(false)
  })

  it('o placeholder diz que a senha está guardada, sem mostrá-la', () => {
    expect(passwordPlaceholder(draftFromAccount(account))).toContain('mantida')
    expect(passwordPlaceholder(emptyMailAccountDraft())).not.toContain('mantida')
  })
})

describe('regra de domínio', () => {
  const base = {
    name: 'aurora-dominio',
    domain: 'auroramoveis.com.br',
    customer_id: 'AURORA',
    queue_name: '',
    stop_after_match: false,
  }

  it('aceita uma regra bem formada', () => {
    expect(validateDomainRule(base)).toEqual([])
  })

  it('recusa e-mail completo no lugar do domínio', () => {
    expect(validateDomainRule({ ...base, domain: 'ana@auroramoveis.com.br' }))
      .toContain('Informe o domínio, não um e-mail completo.')
  })

  it('recusa domínio malformado e cliente vazio', () => {
    expect(validateDomainRule({ ...base, domain: 'aurora' }).length).toBeGreaterThan(0)
    expect(validateDomainRule({ ...base, customer_id: '' }))
      .toContain('Escolha o cliente dono deste domínio.')
  })

  it('aceita o domínio com @ na frente, e o normaliza', () => {
    expect(validateDomainRule({ ...base, domain: '@auroramoveis.com.br' })).toEqual([])
    const payload = buildDomainRulePayload({ ...base, domain: '@auroramoveis.com.br' })
    const match = (payload.match as { key: string, value: string }[])[0]!
    expect(match.value).toContain('auroramoveis')
  })

  it('ESCAPA o ponto no regex — senão um domínio parecido casaria', () => {
    const payload = buildDomainRulePayload(base)
    const value = (payload.match as { key: string, value: string }[])[0]!.value
    expect(value).toBe('@auroramoveis\\.com\\.br$')
    // A prova de que importa: sem escape, este falso-positivo passaria.
    expect(new RegExp(value).test('ana@auroramoveisXcomYbr')).toBe(false)
    expect(new RegExp(value).test('ana@auroramoveis.com.br')).toBe(true)
  })

  it('ancora no fim — subdomínio impostor não casa', () => {
    const value = (buildDomainRulePayload(base).match as { key: string, value: string }[])[0]!.value
    expect(new RegExp(value).test('ana@auroramoveis.com.br.golpe.com')).toBe(false)
  })

  it('atribui o cliente, e a fila só quando informada', () => {
    const semFila = buildDomainRulePayload(base).set as { key: string }[]
    expect(semFila.map(p => p.key)).toEqual(['X-OTRS-CustomerNo'])
    const comFila = buildDomainRulePayload({ ...base, queue_name: 'Suporte::N1' }).set as { key: string }[]
    expect(comFila.map(p => p.key)).toEqual(['X-OTRS-CustomerNo', 'X-OTRS-Queue'])
  })
})

describe('leitura de um filtro existente', () => {
  const filter: PostMasterFilter = {
    name: 'aurora-dominio',
    stop_after_match: false,
    match: [{ key: 'From', value: '@auroramoveis\\.com\\.br$' }],
    set: [{ key: 'X-OTRS-CustomerNo', value: 'AURORA' }],
  }

  it('extrai domínio e cliente para a tabela', () => {
    expect(domainOfFilter(filter)).toContain('auroramoveis')
    expect(customerOfFilter(filter)).toBe('AURORA')
  })

  it('filtro que não casa From nem atribui cliente devolve null', () => {
    const outro: PostMasterFilter = {
      name: 'x', stop_after_match: false,
      match: [{ key: 'Subject', value: 'spam' }],
      set: [{ key: 'X-OTRS-Ignore', value: 'yes' }],
    }
    expect(domainOfFilter(outro)).toBeNull()
    expect(customerOfFilter(outro)).toBeNull()
  })
})

describe('guard do nome de filtro (proxy)', () => {
  it('aceita nome normal e recusa path traversal', () => {
    expect(isFilterName('aurora-dominio')).toBe(true)
    expect(isFilterName('Aurora Domínios')).toBe(false) // acento fora da allowlist
    expect(isFilterName('../../etc/passwd')).toBe(false)
    expect(isFilterName('')).toBe(false)
    expect(isFilterName(undefined)).toBe(false)
  })
})

describe('a ressalva do A9.6 fica na tela', () => {
  it('explica que o remetente segue a fila ATUAL, não a porta de entrada', () => {
    expect(OUTBOUND_WARNING).toContain('fila ONDE O CHAMADO ESTÁ')
    expect(OUTBOUND_WARNING).toContain('move')
  })
})
