<script setup lang="ts">
import type { ContractType } from '#shared/contracts'
import { CONTRACT_TYPES, initialFieldFor, typeLabel } from '#shared/contracts'

definePageMeta({ middleware: 'admin-auth' })

const route = useRoute()
const tenantId = route.params.id as string

const typeOptions = CONTRACT_TYPES.map(t => ({ label: typeLabel(t), value: t }))

const form = reactive({
  code: '',
  type: 'credit_brl' as ContractType,
  starts_on: '',
  ends_on: '',
  initial_value: '' as string,
  unit_price_brl: '' as string,
  travel_franchise_count: 0,
  billing_period_months: 1,
  closing_period_months: 1,
  billing_in_advance: true,
  accumulate_balance_between_cycles: false,
})

// Campo numérico inicial ADAPTA ao tipo (helper PURO, unit-testado).
const initialSpec = computed(() => initialFieldFor(form.type))

const submitting = ref(false)
const errorMsg = ref('')

function validate(): string | null {
  if (!form.code.trim()) return 'Código do contrato é obrigatório.'
  if (!form.starts_on) return 'Data de início é obrigatória.'
  if (!form.ends_on) return 'Data de término é obrigatória.'
  if (form.initial_value === '' || Number.isNaN(Number(form.initial_value))) {
    return `${initialSpec.value.label} é obrigatório.`
  }
  return null
}

async function submit() {
  errorMsg.value = ''
  const v = validate()
  if (v) { errorMsg.value = v; return }

  submitting.value = true
  try {
    const body: Record<string, unknown> = {
      code: form.code.trim(),
      type: form.type,
      starts_on: form.starts_on,
      ends_on: form.ends_on,
      travel_franchise_count: Number(form.travel_franchise_count) || 0,
      billing_period_months: Number(form.billing_period_months) || 1,
      closing_period_months: Number(form.closing_period_months) || 1,
      billing_in_advance: form.billing_in_advance,
      accumulate_balance_between_cycles: form.accumulate_balance_between_cycles,
    }
    // Apenas o campo inicial exigido pelo tipo é enviado.
    body[initialSpec.value.field] = Number(form.initial_value)
    if (form.unit_price_brl !== '' && !Number.isNaN(Number(form.unit_price_brl))) {
      body.unit_price_brl = Number(form.unit_price_brl)
    }

    await $fetch(`/api/admin/tenants/${tenantId}/contracts`, {
      method: 'POST',
      body,
    })
    await navigateTo(`/clientes/${tenantId}`)
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: string } }
    if (err.statusCode === 404) {
      errorMsg.value = err.data?.detail || 'Cliente não encontrado.'
    }
    else if (err.statusCode === 409) {
      errorMsg.value = err.data?.detail || 'Já existe um contrato com este código.'
    }
    else {
      errorMsg.value = err.data?.detail || 'Falha ao criar o contrato. Verifique os dados.'
    }
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-2xl px-5 py-10">
    <ULink :to="`/clientes/${tenantId}`" class="inline-flex items-center gap-1 text-sm text-muted hover:text-default">
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" />
      Voltar para o cliente
    </ULink>
    <h1 class="mt-2 mb-1 font-display text-3xl font-extrabold tracking-tight text-highlighted">
      Novo contrato
    </h1>
    <p class="mb-8 text-sm text-muted">
      Os campos numéricos se ajustam ao tipo de contrato selecionado.
    </p>

    <form class="space-y-6" @submit.prevent="submit">
      <UAlert
        v-if="errorMsg"
        color="error"
        variant="soft"
        icon="i-lucide-alert-triangle"
        :title="errorMsg"
      />

      <div class="grid gap-4 sm:grid-cols-2">
        <UFormField label="Código" required>
          <UInput v-model="form.code" placeholder="CT-2026-001" />
        </UFormField>
        <UFormField label="Tipo" required>
          <USelect v-model="form.type" :items="typeOptions" />
        </UFormField>
        <UFormField label="Início" required>
          <UInput v-model="form.starts_on" type="date" />
        </UFormField>
        <UFormField label="Término" required>
          <UInput v-model="form.ends_on" type="date" />
        </UFormField>

        <!-- Campo inicial ADAPTA ao tipo -->
        <UFormField :label="initialSpec.label" required class="sm:col-span-2">
          <UInput
            v-model="form.initial_value"
            type="number"
            :step="initialSpec.step"
            min="0"
            :placeholder="initialSpec.unit === 'brl' ? '0,00' : '0'"
          />
        </UFormField>

        <UFormField label="Preço unitário (R$)" help="Opcional — para tarifação por hora/serviço">
          <UInput v-model="form.unit_price_brl" type="number" step="0.01" min="0" placeholder="0,00" />
        </UFormField>
        <UFormField label="Franquia de deslocamentos">
          <UInput v-model.number="form.travel_franchise_count" type="number" min="0" />
        </UFormField>
        <UFormField label="Período de faturamento (meses)">
          <UInput v-model.number="form.billing_period_months" type="number" min="1" />
        </UFormField>
        <UFormField label="Período de fechamento (meses)">
          <UInput v-model.number="form.closing_period_months" type="number" min="1" />
        </UFormField>
      </div>

      <div class="space-y-3">
        <UCheckbox v-model="form.billing_in_advance" label="Faturamento antecipado" />
        <UCheckbox v-model="form.accumulate_balance_between_cycles" label="Acumular saldo entre ciclos" />
      </div>

      <div class="flex items-center gap-3">
        <UButton type="submit" color="primary" size="lg" :loading="submitting" icon="i-lucide-check">
          Criar contrato
        </UButton>
        <UButton :to="`/clientes/${tenantId}`" variant="ghost" color="neutral" :disabled="submitting">
          Cancelar
        </UButton>
      </div>
    </form>
  </div>
</template>
