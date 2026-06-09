import { describe, expect, it } from 'vitest'
import { deployStateColor, inciStateColor } from '../components/asset/asset-labels'

// Smoke do fluxo de ativos (#1K fase 3).
//
// HARNESS: mesmo padrão de ticketing-flow.test.ts / portal-roles.test.ts —
// testes de lógica pura (plain vitest + happy-dom), SEM montar as pages (que
// usam <script setup> + composables Nuxt indisponíveis sem boot completo).
//
//   ✓ deployStateColor / inciStateColor: mapeamento SEMÂNTICO (info/success/
//     warning/error/neutral) — NUNCA a cor da marca (H8).
//   ✓ ticketFromAssetPath: link "abrir chamado a partir do ativo" → ?ativo=<id>
//   ✓ buildFormData: inclui config_item_id quando a query ?ativo está presente.

// ─── Badges semânticos (replicado de pages/ativos/* via import direto) ────────

const SEMANTIC = new Set(['success', 'warning', 'error', 'info', 'neutral'])

describe('deployStateColor: cores semânticas do estado de implantação', () => {
  it('Production → success', () => {
    expect(deployStateColor('Production')).toBe('success')
  })
  it('Maintenance / Planned → warning', () => {
    expect(deployStateColor('Maintenance')).toBe('warning')
    expect(deployStateColor('Planned')).toBe('warning')
  })
  it('Retired / Inactive → neutral', () => {
    expect(deployStateColor('Retired')).toBe('neutral')
    expect(deployStateColor('Inactive')).toBe('neutral')
  })
  it('vazio/null → neutral', () => {
    expect(deployStateColor('')).toBe('neutral')
    expect(deployStateColor(null)).toBe('neutral')
    expect(deployStateColor(undefined)).toBe('neutral')
  })
  it('desconhecido → info (fallback, nunca a marca)', () => {
    expect(deployStateColor('Qualquer')).toBe('info')
  })
  it('só usa tokens semânticos (H8: nunca a cor da marca)', () => {
    for (const s of ['Production', 'Maintenance', 'Retired', '', 'xyz']) {
      expect(SEMANTIC.has(deployStateColor(s))).toBe(true)
    }
  })
})

describe('inciStateColor: cores semânticas do estado de incidente', () => {
  it('Operational → success', () => {
    expect(inciStateColor('Operational')).toBe('success')
  })
  it('Warning → warning', () => {
    expect(inciStateColor('Warning')).toBe('warning')
  })
  it('Incident / Failure → error', () => {
    expect(inciStateColor('Incident')).toBe('error')
    expect(inciStateColor('Failure')).toBe('error')
  })
  it('vazio/null → neutral', () => {
    expect(inciStateColor('')).toBe('neutral')
    expect(inciStateColor(null)).toBe('neutral')
  })
  it('só usa tokens semânticos (H8: nunca a cor da marca)', () => {
    for (const s of ['Operational', 'Warning', 'Incident', '', 'xyz']) {
      expect(SEMANTIC.has(inciStateColor(s))).toBe(true)
    }
  })
})

// ─── Link "abrir chamado a partir do ativo" (replicado de ativos/[id].vue) ────

function ticketFromAssetPath(assetId: string): string {
  return `/tickets/novo?ativo=${assetId}`
}

describe('ticketFromAssetPath: link de abrir chamado a partir do ativo', () => {
  it('monta /tickets/novo?ativo=<id>', () => {
    expect(ticketFromAssetPath('42')).toBe('/tickets/novo?ativo=42')
  })
  it('preserva o id como string', () => {
    expect(ticketFromAssetPath('1001')).toBe('/tickets/novo?ativo=1001')
  })
})

// ─── FormData de /tickets/novo com vínculo de ativo (replicado de novo.vue) ───

// Lê route.query.ativo (string | string[] | undefined) → id ('' = ausente).
function resolveAssetId(raw: string | string[] | undefined): string {
  const v = Array.isArray(raw) ? raw[0] : raw
  return v ? String(v) : ''
}

function buildFormData(
  form: { title: string, body: string, contractId?: string },
  selectorVisible: boolean,
  assetId: string,
): Record<string, string> {
  const fd: Record<string, string> = {}
  fd.title = form.title.trim()
  fd.body = form.body.trim()
  if (selectorVisible && form.contractId) fd.contract_id = form.contractId
  if (assetId) fd.config_item_id = assetId
  return fd
}

describe('resolveAssetId: leitura da query ?ativo', () => {
  it('string → o próprio id', () => {
    expect(resolveAssetId('7')).toBe('7')
  })
  it('array (query repetida) → primeiro elemento', () => {
    expect(resolveAssetId(['7', '8'])).toBe('7')
  })
  it('ausente → string vazia', () => {
    expect(resolveAssetId(undefined)).toBe('')
  })
})

describe('buildFormData: config_item_id quando ?ativo está presente', () => {
  it('com assetId → inclui config_item_id', () => {
    const fd = buildFormData({ title: 'Falha', body: 'Detalhes' }, false, '42')
    expect(fd.config_item_id).toBe('42')
  })
  it('sem assetId → omite config_item_id', () => {
    const fd = buildFormData({ title: 'Falha', body: 'Detalhes' }, false, '')
    expect(fd).not.toHaveProperty('config_item_id')
  })
  it('coexiste com contract_id quando o seletor está visível', () => {
    const fd = buildFormData({ title: 'Falha', body: 'Detalhes', contractId: 'c2' }, true, '42')
    expect(fd.contract_id).toBe('c2')
    expect(fd.config_item_id).toBe('42')
  })
})
