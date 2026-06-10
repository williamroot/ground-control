// #1R-a Task 7 — página Agentes no console (instalar/listar/aprovar/revogar).
// Componentes em HTML/SVG nativo (sem U*/@nuxt/icon) montam limpo no vitest
// (lição #1M..#1Q). Testa: comando de instalação + copy, status semântico (H8),
// emissão approve/revoke, e a lógica pura (offline por last_seen, cor/label).
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import DeviceRow from '../components/agent/DeviceRow.vue'
import InstallCommand from '../components/agent/InstallCommand.vue'
import {
  buildInstallCommand,
  deviceStatusColor,
  deviceStatusLabel,
  effectiveStatus,
  isOffline,
} from '../composables/useAgents'

describe('buildInstallCommand', () => {
  it('monta curl install.sh | sh -s -- --enroll-token --server', () => {
    const cmd = buildInstallCommand('https://api-dev.was.dev.br', 'gcat_ABC')
    expect(cmd).toContain('install.sh')
    expect(cmd).toContain('| sh -s --')
    expect(cmd).toContain('--enroll-token=gcat_ABC')
    expect(cmd).toContain('--server=https://api-dev.was.dev.br')
  })
})

describe('effectiveStatus / isOffline', () => {
  const interval = 3600
  it('active recente = active', () => {
    const recent = new Date().toISOString()
    expect(isOffline(recent, interval)).toBe(false)
    expect(effectiveStatus('active', recent, interval)).toBe('active')
  })
  it('active sem contato > 2x intervalo = offline', () => {
    const old = new Date(Date.now() - 3 * interval * 1000).toISOString()
    expect(isOffline(old, interval)).toBe(true)
    expect(effectiveStatus('active', old, interval)).toBe('offline')
  })
  it('pending/revoked nunca viram offline', () => {
    const old = new Date(Date.now() - 99 * interval * 1000).toISOString()
    expect(effectiveStatus('pending', old, interval)).toBe('pending')
    expect(effectiveStatus('revoked', old, interval)).toBe('revoked')
  })
  it('active sem last_seen = offline', () => {
    expect(isOffline(null, interval)).toBe(true)
  })
})

describe('deviceStatusColor (H8 semântica)', () => {
  it('active=success pending=warning offline=neutral revoked=error', () => {
    expect(deviceStatusColor('active')).toBe('success')
    expect(deviceStatusColor('pending')).toBe('warning')
    expect(deviceStatusColor('offline')).toBe('neutral')
    expect(deviceStatusColor('revoked')).toBe('error')
  })
  it('rótulos em PT-BR', () => {
    expect(deviceStatusLabel('active')).toMatch(/ativo/i)
    expect(deviceStatusLabel('pending')).toMatch(/pendente/i)
    expect(deviceStatusLabel('offline')).toMatch(/offline/i)
    expect(deviceStatusLabel('revoked')).toMatch(/revog/i)
  })
})

describe('InstallCommand', () => {
  it('renderiza o comando e copia para a área de transferência', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
    const w = mount(InstallCommand, {
      props: { server: 'https://api-dev.was.dev.br', token: 'gcat_XYZ' },
    })
    const html = w.html()
    expect(html).toContain('--enroll-token=gcat_XYZ')
    expect(html).toContain('install.sh')
    await w.find('[data-testid="copy-install"]').trigger('click')
    expect(writeText).toHaveBeenCalledOnce()
    expect(writeText.mock.calls[0][0]).toContain('gcat_XYZ')
  })
})

describe('DeviceRow', () => {
  const device = {
    id: 'd1',
    hostname: 'aur-nb-1',
    status: 'pending',
    os: 'Ubuntu',
    fingerprint: 'FP1',
    znuny_config_item_id: null,
    specs: { cpu: 'i5', memory: '16 GB' },
    last_seen_at: null,
    enrolled_at: new Date().toISOString(),
  }

  it('mostra hostname/os e emite approve quando pending', async () => {
    const w = mount(DeviceRow, { props: { device, heartbeatInterval: 3600 } })
    expect(w.html()).toContain('aur-nb-1')
    expect(w.html()).toContain('Ubuntu')
    await w.find('[data-testid="approve"]').trigger('click')
    expect(w.emitted('approve')?.[0]).toEqual(['d1'])
  })

  it('emite revoke', async () => {
    const active = { ...device, status: 'active', last_seen_at: new Date().toISOString() }
    const w = mount(DeviceRow, { props: { device: active, heartbeatInterval: 3600 } })
    await w.find('[data-testid="revoke"]').trigger('click')
    expect(w.emitted('revoke')?.[0]).toEqual(['d1'])
  })

  it('device revogado não oferece approve/revoke', () => {
    const revoked = { ...device, status: 'revoked' }
    const w = mount(DeviceRow, { props: { device: revoked, heartbeatInterval: 3600 } })
    expect(w.find('[data-testid="approve"]').exists()).toBe(false)
    expect(w.find('[data-testid="revoke"]').exists()).toBe(false)
  })
})
