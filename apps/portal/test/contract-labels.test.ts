import { describe, expect, it } from 'vitest'
import { statusColor, statusLabel, typeLabel } from '../components/contract/labels'

describe('contract labels', () => {
  it('typeLabel maps enums to PT', () => {
    expect(typeLabel('credit_brl')).toBe('Crédito (R$)')
    expect(typeLabel('hour_bank')).toBe('Banco de horas')
    expect(typeLabel('service_count')).toBe('Pacote de serviços')
  })
  it('typeLabel falls back to raw for unknown', () => {
    expect(typeLabel('mystery')).toBe('mystery')
  })
  it('statusLabel + statusColor map enums', () => {
    expect(statusLabel('active')).toBe('Ativo')
    expect(statusColor('active')).toBe('success')
    expect(statusLabel('suspended')).toBe('Suspenso')
    expect(statusColor('suspended')).toBe('warning')
    expect(statusColor('expired')).toBe('error')
  })
  it('status falls back to neutral for unknown', () => {
    expect(statusLabel('weird')).toBe('weird')
    expect(statusColor('weird')).toBe('neutral')
  })
})
