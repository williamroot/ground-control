<script setup lang="ts">
// Editor de regra de automação (#1Q). `ruleId === 'novo'` → criação; senão edição.
// `?tenant=<id>` define o tenant. Lista dinâmica de condições/ações (add/remove),
// montagem e validação via composables/useAutomationRule (espelho do server).
import ActionRow from '../../components/automation/ActionRow.vue'
import ConditionRow from '../../components/automation/ConditionRow.vue'
import {
  type AutomationMeta,
  buildRulePayload,
  emptyAction,
  emptyCondition,
  emptyDraft,
  isRuleValid,
  type RuleDraft,
  validateRule,
} from '../../composables/useAutomationRule'

definePageMeta({ middleware: 'admin-auth' })

const route = useRoute()
const router = useRouter()
const ruleId = computed(() => String(route.params.ruleId))
const tenantId = computed(() => String(route.query.tenant ?? ''))
const isNew = computed(() => ruleId.value === 'novo')

const headers = useRequestHeaders(['cookie'])
const { data: meta } = await useAsyncData('automation-meta', () =>
  $fetch<AutomationMeta>('/api/admin/automation/meta', { headers })
    .catch(() => ({ fields: [], ops: [], actions: [], trigger_events: [] }) as AutomationMeta))

const draft = ref<RuleDraft>(emptyDraft())

if (!isNew.value) {
  const rules = await $fetch<RuleDraft[] & { id: string }[]>(
    `/api/admin/tenants/${tenantId.value}/automation-rules`,
    { headers },
  ).catch(() => [])
  const found = (rules as unknown as (RuleDraft & { id: string })[]).find(r => r.id === ruleId.value)
  if (found) {
    draft.value = {
      name: found.name,
      trigger_event: found.trigger_event,
      conditions: (found.conditions ?? []).map(c => ({
        field: c.field, op: c.op, value: String(c.value ?? ''),
      })),
      actions: (found.actions ?? []).map(a => ({ type: a.type, params: { ...a.params } })),
      position: found.position,
      enabled: found.enabled,
    }
  }
}

const metaSafe = computed<AutomationMeta>(() =>
  meta.value ?? { fields: [], ops: [], actions: [], trigger_events: [] })

const errors = computed(() => validateRule(draft.value, metaSafe.value))
const canSave = computed(() => isRuleValid(draft.value, metaSafe.value))
const saving = ref(false)
const saveError = ref('')

function addCondition() {
  draft.value.conditions.push(emptyCondition())
}
function removeCondition(i: number) {
  draft.value.conditions.splice(i, 1)
}
function addAction() {
  draft.value.actions.push(emptyAction())
}
function removeAction(i: number) {
  draft.value.actions.splice(i, 1)
}

async function save() {
  if (!canSave.value) return
  saving.value = true
  saveError.value = ''
  const payload = buildRulePayload(draft.value)
  try {
    if (isNew.value) {
      await $fetch(`/api/admin/tenants/${tenantId.value}/automation-rules`, {
        method: 'POST', body: payload,
      })
    }
    else {
      await $fetch(`/api/admin/tenants/${tenantId.value}/automation-rules/${ruleId.value}`, {
        method: 'PUT', body: payload,
      })
    }
    await router.push('/automacoes')
  }
  catch (e) {
    saveError.value = (e as { data?: { detail?: string } })?.data?.detail ?? 'erro ao salvar'
  }
  finally {
    saving.value = false
  }
}

async function remove() {
  if (isNew.value) return
  saving.value = true
  try {
    await $fetch(`/api/admin/tenants/${tenantId.value}/automation-rules/${ruleId.value}`, {
      method: 'DELETE',
    })
    await router.push('/automacoes')
  }
  finally {
    saving.value = false
  }
}

const triggerOptions = computed(() =>
  metaSafe.value.trigger_events.map(t => ({ label: t, value: t })))
</script>

<template>
  <div class="mx-auto max-w-3xl px-5 py-10">
    <header class="mb-8">
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        {{ isNew ? 'Nova regra' : 'Editar regra' }}
      </h1>
      <p class="mt-1 text-sm text-muted">
        Condições em AND; ações executadas quando todas casam, no evento real.
      </p>
    </header>

    <div class="space-y-6">
      <UFormField label="Nome">
        <UInput v-model="draft.name" placeholder="Ex.: Escalar tickets urgentes" />
      </UFormField>

      <UFormField label="Gatilho (evento)">
        <USelect v-model="draft.trigger_event" :items="triggerOptions" placeholder="Selecione" />
      </UFormField>

      <div class="flex items-center gap-3">
        <USwitch v-model="draft.enabled" />
        <span class="text-sm text-muted">{{ draft.enabled ? 'Ativa' : 'Desativada' }}</span>
      </div>

      <UFormField label="Ordem de avaliação">
        <UInput v-model.number="draft.position" type="number" class="max-w-[8rem]" />
      </UFormField>

      <!-- Condições -->
      <section class="space-y-3">
        <div class="flex items-center justify-between">
          <h2 class="font-display text-lg font-bold text-highlighted">Condições</h2>
          <UButton size="xs" variant="soft" icon="i-lucide-plus" @click="addCondition">
            Adicionar condição
          </UButton>
        </div>
        <p v-if="draft.conditions.length === 0" class="text-sm text-muted">
          Sem condições — a regra dispara em todo evento do gatilho.
        </p>
        <ConditionRow
          v-for="(c, i) in draft.conditions"
          :key="`cond-${i}`"
          v-model="draft.conditions[i]"
          :fields="metaSafe.fields"
          :ops="metaSafe.ops"
          @remove="removeCondition(i)"
        />
      </section>

      <!-- Ações -->
      <section class="space-y-3">
        <div class="flex items-center justify-between">
          <h2 class="font-display text-lg font-bold text-highlighted">Ações</h2>
          <UButton size="xs" variant="soft" icon="i-lucide-plus" @click="addAction">
            Adicionar ação
          </UButton>
        </div>
        <ActionRow
          v-for="(a, i) in draft.actions"
          :key="`act-${i}`"
          v-model="draft.actions[i]"
          :actions="metaSafe.actions"
          @remove="removeAction(i)"
        />
      </section>

      <UAlert
        v-if="errors.length > 0"
        color="warning"
        variant="soft"
        :title="`Ajuste antes de salvar (${errors.length})`"
        :description="errors.join(' · ')"
      />
      <UAlert v-if="saveError" color="error" variant="soft" :title="saveError" />

      <div class="flex items-center gap-3 pt-2">
        <UButton :disabled="!canSave || saving" :loading="saving" color="primary" @click="save">
          {{ isNew ? 'Criar regra' : 'Salvar' }}
        </UButton>
        <UButton to="/automacoes" color="neutral" variant="ghost">Cancelar</UButton>
        <UButton
          v-if="!isNew"
          color="error"
          variant="ghost"
          class="ml-auto"
          :disabled="saving"
          @click="remove"
        >
          Excluir
        </UButton>
      </div>
    </div>
  </div>
</template>
