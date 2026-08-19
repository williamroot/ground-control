<script setup lang="ts">
import type { ChecklistTemplate } from '~/composables/useChecklists'
import { parseItems, validateTemplate } from '~/composables/useChecklists'

// R13b — modelos de checklist. São procedimento da GERTI (onboarding de
// estação, troca de servidor), não de um cliente: por isso a tela é global e
// não vive dentro de um cliente.
definePageMeta({ middleware: 'admin-auth' })

const headers = useRequestHeaders(['cookie'])
const toast = useToast()

const { data: templates, refresh } = await useAsyncData('checklist-templates-admin', () =>
  $fetch<ChecklistTemplate[] | null>('/api/admin/checklists/templates?include_inactive=true', {
    headers,
  }).catch(() => null))

const name = ref('')
const description = ref('')
const itemsText = ref('')
const saving = ref(false)

// Erro só depois que a pessoa mexeu — ver o mesmo cuidado em /licencas.
const touched = ref(false)
watch([name, itemsText], () => { touched.value = true })

const errors = computed(() => validateTemplate(name.value, itemsText.value))
const preview = computed(() => parseItems(itemsText.value))

async function create() {
  if (errors.value.length) return
  saving.value = true
  try {
    await $fetch('/api/admin/checklists/templates', {
      method: 'POST',
      body: {
        name: name.value.trim(),
        description: description.value.trim() || null,
        items: preview.value,
      },
    })
    toast.add({ title: 'Modelo criado', color: 'success' })
    name.value = ''
    description.value = ''
    itemsText.value = ''
    await refresh()
  }
  catch (e) {
    const err = e as { data?: { detail?: string } }
    toast.add({ title: 'Não foi possível criar', description: err.data?.detail, color: 'error' })
  }
  finally {
    saving.value = false
  }
}

async function deactivate(t: ChecklistTemplate) {
  try {
    await $fetch(`/api/admin/checklists/templates/${t.id}`, { method: 'DELETE' })
    toast.add({ title: `${t.name} desativado`, color: 'neutral' })
    await refresh()
  }
  catch {
    toast.add({ title: 'Falha ao desativar', color: 'error' })
  }
}
</script>

<template>
  <div class="mx-auto max-w-3xl px-5 py-10">
    <header class="mb-6">
      <h1 class="font-display text-2xl font-extrabold tracking-tight text-highlighted">
        Checklists
      </h1>
      <p class="mt-1 text-sm text-muted">
        Procedimentos que o técnico segue durante o atendimento. O modelo é seu, a execução
        é por chamado.
      </p>
    </header>

    <UCard class="mb-6">
      <template #header>
        <h2 class="font-display text-base font-bold text-highlighted">Novo modelo</h2>
      </template>

      <div class="space-y-3">
        <UFormField label="Nome">
          <UInput v-model="name" placeholder="Onboarding de estação" class="w-full" />
        </UFormField>
        <UFormField label="Descrição (opcional)">
          <UInput v-model="description" placeholder="Quando usar este procedimento" class="w-full" />
        </UFormField>
        <UFormField label="Itens" help="Um por linha, na ordem em que devem ser feitos.">
          <UTextarea
            v-model="itemsText"
            :rows="6"
            placeholder="Criar usuário no domínio&#10;Instalar antivírus&#10;Configurar impressora&#10;Entregar termo assinado"
            class="w-full"
          />
        </UFormField>
      </div>

      <p v-if="preview.length" class="mt-3 text-xs text-muted">
        {{ preview.length }} {{ preview.length === 1 ? 'item' : 'itens' }} —
        o técnico vai marcar um a um.
      </p>
      <ul v-if="touched && errors.length" class="mt-3 list-disc pl-5 text-sm text-error">
        <li v-for="err in errors" :key="err">{{ err }}</li>
      </ul>

      <template #footer>
        <UButton
          :loading="saving"
          :disabled="errors.length > 0"
          icon="i-lucide-plus"
          label="Criar modelo"
          @click="create"
        />
      </template>
    </UCard>

    <UCard>
      <template #header>
        <h2 class="font-display text-base font-bold text-highlighted">Modelos</h2>
      </template>

      <p v-if="!templates || templates.length === 0" class="text-sm text-muted">
        Nenhum modelo cadastrado ainda.
      </p>

      <div
        v-for="t in templates ?? []"
        :key="t.id"
        class="mb-4 rounded-xl border border-default p-4 last:mb-0"
      >
        <div class="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 class="font-semibold text-highlighted">
              {{ t.name }}
              <UBadge v-if="!t.active" color="neutral" variant="soft" size="sm" class="ml-1">
                inativo
              </UBadge>
            </h3>
            <p v-if="t.description" class="text-sm text-muted">{{ t.description }}</p>
          </div>
          <UButton
            v-if="t.active"
            size="xs"
            color="neutral"
            variant="ghost"
            icon="i-lucide-archive"
            label="Desativar"
            @click="deactivate(t)"
          />
        </div>
        <ol class="mt-2 list-decimal pl-5 text-sm text-muted">
          <li v-for="(item, i) in t.items" :key="i">{{ item }}</li>
        </ol>
      </div>

      <template #footer>
        <p class="text-xs text-muted">
          Modelos são <strong>desativados</strong>, nunca apagados — apagar sumiria com o
          histórico de quem já executou o procedimento.
        </p>
      </template>
    </UCard>
  </div>
</template>
