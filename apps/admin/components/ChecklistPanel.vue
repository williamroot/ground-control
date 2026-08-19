<script setup lang="ts">
import type { Checklist, ChecklistTemplate } from '~/composables/useChecklists'
import { availableTemplates, localPercent } from '~/composables/useChecklists'

// R13b — o checklist durante o atendimento.
//
// *"Temos aqui configurações de feriados, checklists personalizáveis."* (08:16)
//
// A marcação é otimista: a barra anda na hora e o servidor confirma depois.
// Sem isso, marcar cinco itens em sequência dá cinco esperas — e checklist é
// justamente o que se usa com as mãos ocupadas.
const props = defineProps<{ ticketId: number }>()

const toast = useToast()
const headers = useRequestHeaders(['cookie'])

const { data: applied, refresh } = await useAsyncData(`checklists-${props.ticketId}`, () =>
  $fetch<Checklist[] | null>(`/api/admin/tickets/${props.ticketId}/checklists`, { headers })
    .catch(() => null))
const { data: templates } = await useAsyncData('checklist-templates', () =>
  $fetch<ChecklistTemplate[] | null>('/api/admin/checklists/templates', { headers })
    .catch(() => null))

const chosen = ref<string>('')
const applying = ref(false)

const options = computed(() =>
  availableTemplates(templates.value ?? [], applied.value ?? [])
    .map(t => ({ label: t.name, value: t.id })))

async function apply() {
  if (!chosen.value) return
  applying.value = true
  try {
    await $fetch(`/api/admin/tickets/${props.ticketId}/checklists`, {
      method: 'POST',
      body: { template_id: chosen.value },
    })
    chosen.value = ''
    await refresh()
  }
  catch (e) {
    const err = e as { data?: { detail?: string } }
    toast.add({
      title: 'Não foi possível aplicar',
      description: err.data?.detail,
      color: 'error',
    })
  }
  finally {
    applying.value = false
  }
}

async function toggle(checklist: Checklist, itemId: string, done: boolean) {
  const item = checklist.items.find(i => i.id === itemId)
  if (!item) return
  const before = item.done
  item.done = done // otimista
  try {
    await $fetch(`/api/admin/tickets/${props.ticketId}/checklist-items/${itemId}`, {
      method: 'PUT',
      body: { done },
    })
    await refresh()
  }
  catch {
    item.done = before // desfaz se o servidor recusou
    toast.add({ title: 'Falha ao marcar o item', color: 'error' })
  }
}
</script>

<template>
  <UCard>
    <template #header>
      <div class="flex items-center justify-between gap-3">
        <h2 class="font-display text-base font-bold text-highlighted">Checklists</h2>
        <div v-if="options.length" class="flex items-center gap-2">
          <USelectMenu
            v-model="chosen"
            :items="options"
            value-key="value"
            placeholder="Aplicar modelo"
            class="min-w-[200px]"
          />
          <UButton
            size="sm"
            variant="soft"
            icon="i-lucide-list-checks"
            label="Aplicar"
            :loading="applying"
            :disabled="!chosen"
            @click="apply"
          />
        </div>
      </div>
    </template>

    <p v-if="!applied || applied.length === 0" class="text-sm text-muted">
      Nenhum checklist aplicado a este chamado.
      <template v-if="!options.length">
        Cadastre um modelo em <ULink to="/checklists" class="text-primary">Checklists</ULink>.
      </template>
    </p>

    <div v-for="cl in applied ?? []" :key="cl.id" class="mb-5 last:mb-0">
      <div class="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h3 class="font-semibold text-highlighted">{{ cl.template_name }}</h3>
        <span class="text-sm text-muted">
          {{ cl.items.filter(i => i.done).length }} de {{ cl.items.length }}
        </span>
      </div>
      <UProgress :model-value="localPercent(cl.items)" class="mb-3" />

      <ul class="space-y-1.5">
        <li v-for="item in cl.items" :key="item.id" class="flex items-start gap-2 text-sm">
          <UCheckbox
            :model-value="item.done"
            @update:model-value="(v: boolean) => toggle(cl, item.id, v)"
          />
          <div>
            <span :class="item.done ? 'text-muted line-through' : 'text-default'">
              {{ item.text }}
            </span>
            <span v-if="item.done && item.done_by" class="ml-2 text-xs text-muted">
              — {{ item.done_by }}
            </span>
          </div>
        </li>
      </ul>

      <p class="mt-2 text-xs text-muted">
        Aplicado por {{ cl.applied_by }} em
        {{ new Date(cl.applied_at).toLocaleDateString('pt-BR') }}.
      </p>
    </div>
  </UCard>
</template>
