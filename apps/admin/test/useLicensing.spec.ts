// R16 — regras da tela de licenciamento.
import { describe, expect, it } from 'vitest'
import {
  enforcementNotice,
  moduleLabel,
  seatTone,
  seatUsagePercent,
  validateAssignment,
  validateSeats,
} from '../composables/useLicensing'

const base = {
  seats_total: 9,
  seats_used: 7,
  seats_free: 2,
  tenants_total: 60,
  contracts_active: 43,
  enforcement_enabled: true,
}

describe('o quadro', () => {
  it('calcula o uso — o caso exato do vídeo (7 de 9)', () => {
    expect(seatUsagePercent(base)).toBe(78)
  })

  it('não passa de 100 quando o teto foi reduzido depois', () => {
    expect(seatUsagePercent({ seats_total: 5, seats_used: 8 })).toBe(100)
  })

  it('sem teto configurado não inventa percentual', () => {
    expect(seatUsagePercent({ seats_total: 0, seats_used: 0 })).toBe(0)
  })

  it('lotado é erro, não aviso', () => {
    // Com o teto batido a próxima contratação FALHA — o operador precisa
    // saber antes de prometer acesso a alguém.
    expect(seatTone({ seats_total: 9, seats_used: 9 })).toBe('error')
    expect(seatTone({ seats_total: 9, seats_used: 8 })).toBe('warning')
    expect(seatTone({ seats_total: 9, seats_used: 3 })).toBe('neutral')
  })
})

describe('o aviso do gate desligado', () => {
  it('aparece quando os módulos não restringem nada', () => {
    const notice = enforcementNotice({ ...base, enforcement_enabled: false })
    expect(notice).toContain('NÃO restringem')
    expect(notice).toContain('LICENSE_ENFORCEMENT_ENABLED')
  })

  it('some quando o gate está ligado', () => {
    expect(enforcementNotice(base)).toBeNull()
  })
})

describe('atribuição', () => {
  it('exige o login', () => {
    expect(validateAssignment('  ', ['tickets'], base, null)).toContain(
      'Informe o login do agente.',
    )
  })

  it('recusa sem seat livre, com a contagem', () => {
    const full = { ...base, seats_used: 9, seats_free: 0 }
    const errors = validateAssignment('georgia', ['tickets'], full, null)
    expect(errors[0]).toContain('9 de 9')
  })

  it('editar módulos de quem já tem licença não consome seat', () => {
    const full = { ...base, seats_used: 9, seats_free: 0 }
    const existing = {
      agent_login: 'georgia', active: true, modules: ['tickets'],
      assigned_at: '', assigned_by: null, revoked_at: null,
    }
    expect(validateAssignment('georgia', ['tickets', 'inventory'], full, existing)).toEqual([])
  })

  it('reativar um revogado consome seat', () => {
    // Senão o teto seria burlável revogando e reativando.
    const full = { ...base, seats_used: 9, seats_free: 0 }
    const revoked = {
      agent_login: 'georgia', active: false, modules: [],
      assigned_at: '', assigned_by: null, revoked_at: '2026-08-01',
    }
    expect(validateAssignment('georgia', ['tickets'], full, revoked)).toHaveLength(1)
  })
})

describe('total contratado', () => {
  it('recusa reduzir abaixo do que está em uso', () => {
    expect(validateSeats(3, base)[0]).toContain('7 licenças em uso')
  })

  it('aceita aumentar', () => {
    expect(validateSeats(12, base)).toEqual([])
  })

  it('recusa número inválido', () => {
    expect(validateSeats(-1, base)).toHaveLength(1)
    expect(validateSeats(1.5, base)).toHaveLength(1)
  })
})

describe('rótulos', () => {
  it('usa o catálogo vindo do servidor e cai no valor cru se não achar', () => {
    const opts = [{ value: 'tickets', label: 'Chamados' }]
    expect(moduleLabel('tickets', opts)).toBe('Chamados')
    expect(moduleLabel('inventory', opts)).toBe('inventory')
  })
})
