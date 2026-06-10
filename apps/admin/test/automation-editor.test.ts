// #1Q Task 6 — editor de regras de automação.
// Componentes em HTML nativo (sem U*/@nuxt/icon) montam limpo no vitest (lição
// #1M..#1P). Testa: emissão dos rows + lógica pura de montagem/validação.
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ActionRow from '../components/automation/ActionRow.vue'
import ConditionRow from '../components/automation/ConditionRow.vue'
import {
  type AutomationMeta,
  buildRulePayload,
  emptyDraft,
  isRuleValid,
  validateRule,
} from '../composables/useAutomationRule'

const META: AutomationMeta = {
  fields: ['priority', 'title', 'state', 'age_minutes'],
  ops: ['eq', 'ne', 'contains', 'gt', 'lt'],
  actions: ['set_priority', 'add_note', 'ai_summarize_note'],
  trigger_events: ['ticket_create', 'article_create', 'state_update', 'escalation'],
}

describe('ConditionRow', () => {
  it('emite {field, op, value} ao mudar os dropdowns', async () => {
    const wrapper = mount(ConditionRow, {
      props: { modelValue: { field: '', op: 'eq', value: '' }, fields: META.fields, ops: META.ops },
    })
    await wrapper.find('[data-testid="condition-field"]').setValue('title')
    const ev = wrapper.emitted('update:modelValue')
    expect(ev).toBeTruthy()
    expect((ev!.at(-1)![0] as Record<string, string>).field).toBe('title')
  })

  it('emite remove', async () => {
    const wrapper = mount(ConditionRow, {
      props: { modelValue: { field: 'title', op: 'eq', value: 'x' }, fields: META.fields, ops: META.ops },
    })
    await wrapper.find('[data-testid="condition-remove"]').trigger('click')
    expect(wrapper.emitted('remove')).toBeTruthy()
  })
})

describe('ActionRow', () => {
  it('emite {type, params} e reseta params ao trocar tipo', async () => {
    const wrapper = mount(ActionRow, {
      props: { modelValue: { type: '', params: {} }, actions: META.actions },
    })
    await wrapper.find('[data-testid="action-type"]').setValue('set_priority')
    const ev = wrapper.emitted('update:modelValue')!
    expect((ev.at(-1)![0] as Record<string, unknown>).type).toBe('set_priority')
    expect((ev.at(-1)![0] as { params: object }).params).toEqual({})
  })

  it('escreve o parâmetro principal na chave certa da ação', async () => {
    const wrapper = mount(ActionRow, {
      props: { modelValue: { type: 'set_priority', params: {} }, actions: META.actions },
    })
    await wrapper.find('[data-testid="action-param"]').setValue('5 very high')
    const ev = wrapper.emitted('update:modelValue')!
    expect((ev.at(-1)![0] as { params: Record<string, string> }).params).toEqual({
      priority: '5 very high',
    })
  })

  it('ai_summarize_note não mostra input de parâmetro', () => {
    const wrapper = mount(ActionRow, {
      props: { modelValue: { type: 'ai_summarize_note', params: {} }, actions: META.actions },
    })
    expect(wrapper.find('[data-testid="action-param"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="action-noparam"]').exists()).toBe(true)
  })
})

describe('buildRulePayload + validação', () => {
  it('monta o payload a partir do rascunho', () => {
    const draft = {
      ...emptyDraft(),
      name: '  urgente  ',
      trigger_event: 'article_create',
      conditions: [{ field: 'title', op: 'contains', value: 'urgente' }],
      actions: [{ type: 'set_priority', params: { priority: '5 very high' } }],
      position: 2,
    }
    const p = buildRulePayload(draft)
    expect(p.name).toBe('urgente')
    expect(p.conditions[0]).toEqual({ field: 'title', op: 'contains', value: 'urgente' })
    expect(p.actions[0]).toEqual({ type: 'set_priority', params: { priority: '5 very high' } })
    expect(p.position).toBe(2)
    expect(p.enabled).toBe(true)
  })

  it('bloqueia salvar quando inválido (espelho do server)', () => {
    const invalid = {
      ...emptyDraft(),
      name: '',
      trigger_event: 'nope',
      conditions: [{ field: '__danger__', op: 'regex', value: 'x' }],
      actions: [],
    }
    expect(isRuleValid(invalid, META)).toBe(false)
    const errs = validateRule(invalid, META)
    expect(errs.length).toBeGreaterThan(0)
  })

  it('aceita uma regra válida', () => {
    const ok = {
      ...emptyDraft(),
      name: 'ok',
      trigger_event: 'ticket_create',
      conditions: [{ field: 'priority', op: 'eq', value: '5 very high' }],
      actions: [{ type: 'add_note', params: { note: 'oi' } }],
    }
    expect(isRuleValid(ok, META)).toBe(true)
  })
})
