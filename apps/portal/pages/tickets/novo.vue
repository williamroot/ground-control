<script setup lang="ts">
import type { Branding } from '#shared/branding'
import { DEFAULT_BRANDING } from '#shared/branding'

// #1E fase 3 — Abertura de chamado (form A, página única). Guarda por sessão
// (qualquer papel logado pode abrir). O seletor de contrato é CONDICIONAL
// (D-1E-2): só aparece quando há >= 2 contratos selecionáveis; com 0 ou 1 o
// backend vincula sozinho (single/None) e não pedimos nada ao cliente.
definePageMeta({ middleware: 'auth' })

interface SelectableContract {
  id: string
  code: string
  type: string
  saldo_label: string | null
}
interface MetaItem { Key: string, Value: string }
interface FormMeta {
  services: MetaItem[]
  priorities: MetaItem[]
  types: MetaItem[]
}
interface OpenedTicket {
  znuny_ticket_id: number
  ticket_number: string
  contract_id: string
}

const headers = useRequestHeaders(['cookie'])
const toast = useToast()
const route = useRoute()
const branding = useState<Branding>('branding', () => DEFAULT_BRANDING)
const tenantName = computed(() => branding.value?.display_name ?? 'Portal')

// #1K fase 3 — "abrir chamado a partir do ativo": quando a query ?ativo=<id>
// está presente, o chamado nasce vinculado ao Config Item (config_item_id).
const assetId = computed(() => {
  const raw = route.query.ativo
  const v = Array.isArray(raw) ? raw[0] : raw
  return v ? String(v) : ''
})

// SSR: catálogo de contratos selecionáveis + meta do formulário (serviços,
// prioridades, tipos). Falhas degradam para listas vazias — o form ainda abre.
const { data: contracts } = await useAsyncData('ticketing-contracts', () =>
  $fetch<SelectableContract[]>('/api/portal/ticketing/contracts', { headers })
    .catch(() => [] as SelectableContract[]))
const { data: meta } = await useAsyncData('ticketing-form-meta', () =>
  $fetch<FormMeta>('/api/portal/ticketing/form-meta', { headers })
    .catch(() => ({ services: [], priorities: [], types: [] } as FormMeta)))

const selectableContracts = computed(() => contracts.value ?? [])
// D-1E-2: seletor só quando há ambiguidade (>= 2 contratos ativos).
const showContractSelector = computed(() => selectableContracts.value.length >= 2)

// Opções dos USelect — {label, value} a partir dos pares {Key, Value} do Znuny.
function toOptions(items: MetaItem[] | undefined) {
  return (items ?? []).map(i => ({ label: i.Value, value: i.Key }))
}
const serviceOptions = computed(() => toOptions(meta.value?.services))
const typeOptions = computed(() => toOptions(meta.value?.types))
const priorityOptions = computed(() => toOptions(meta.value?.priorities))
const contractOptions = computed(() =>
  selectableContracts.value.map(c => ({
    label: c.saldo_label ? `${c.code} — ${c.saldo_label}` : c.code,
    value: c.id,
  })))

// Prioridade default: a que contém "normal" (case-insensitive), senão a 1ª.
function defaultPriority(): string | undefined {
  const list = meta.value?.priorities ?? []
  const normal = list.find(p => /normal/i.test(p.Value) || /normal/i.test(p.Key))
  return (normal ?? list[0])?.Key
}

const form = reactive({
  contractId: undefined as string | undefined,
  service: undefined as string | undefined,
  type: undefined as string | undefined,
  priority: defaultPriority(),
  title: '',
  body: '',
})
const files = ref<File[]>([])

const submitting = ref(false)
const contractError = ref('') // erro específico do seletor (422)
const formError = ref('') // erro geral (UAlert)

function onFilesChange(e: Event) {
  const input = e.target as HTMLInputElement
  files.value = input.files ? Array.from(input.files) : []
}
function removeFile(idx: number) {
  files.value = files.value.filter((_, i) => i !== idx)
}
function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

const titleInvalid = computed(() => formError.value !== '' && !form.title.trim())
const bodyInvalid = computed(() => formError.value !== '' && !form.body.trim())

async function submit() {
  contractError.value = ''
  formError.value = ''

  if (!form.title.trim() || !form.body.trim()) {
    formError.value = 'Preencha o assunto e a descrição para abrir o chamado.'
    return
  }
  if (showContractSelector.value && !form.contractId) {
    contractError.value = 'Selecione um contrato.'
    return
  }

  submitting.value = true
  try {
    const fd = new FormData()
    fd.append('title', form.title.trim())
    fd.append('body', form.body.trim())
    if (showContractSelector.value && form.contractId) fd.append('contract_id', form.contractId)
    if (assetId.value) fd.append('config_item_id', assetId.value)
    if (form.service) fd.append('service', form.service)
    if (form.type) fd.append('type', form.type)
    if (form.priority) fd.append('priority', form.priority)
    for (const f of files.value) fd.append('files', f, f.name)

    // NÃO setar content-type: o browser define o boundary do multipart.
    const resp = await $fetch<OpenedTicket>('/api/portal/tickets', {
      method: 'POST',
      body: fd,
    })

    toast.add({
      title: 'Chamado aberto',
      description: `Protocolo ${resp.ticket_number} criado com sucesso.`,
      color: 'success',
      icon: 'i-lucide-check-circle',
    })
    await navigateTo(`/tickets/${resp.znuny_ticket_id}`)
  }
  catch (err: unknown) {
    const e = err as { status?: number, statusCode?: number, data?: { detail?: string } }
    const status = e.status ?? e.statusCode
    const detail = e.data?.detail ?? ''
    if (status === 422 || detail === 'contract_required') {
      contractError.value = 'Selecione um contrato para vincular este chamado.'
    }
    else if (status === 404 && detail === 'contract_not_found') {
      formError.value = 'Nenhum contrato ativo foi encontrado para vincular o chamado. '
        + 'Fale com o suporte se acredita que isto é um engano.'
    }
    else if (status === 413) {
      formError.value = 'Um dos anexos é grande demais (limite de 10 MB por arquivo).'
    }
    else if (status === 415) {
      formError.value = 'Tipo de anexo não permitido. Use PNG, JPG, PDF, TXT, LOG, CSV, ZIP ou DOC.'
    }
    else if (status === 503) {
      formError.value = 'O sistema de chamados está indisponível no momento. Tente novamente em instantes.'
    }
    else {
      formError.value = 'Não foi possível abrir o chamado. Verifique os dados e tente novamente.'
    }
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-2xl px-5 py-8">
    <NuxtLink
      to="/tickets"
      class="mb-6 inline-flex items-center gap-1.5 text-sm text-muted transition hover:text-highlighted"
    >
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" /> Voltar para chamados
    </NuxtLink>

    <header class="mb-8">
      <p class="text-sm text-muted">{{ tenantName }}</p>
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Abrir chamado
      </h1>
      <p class="mt-1 text-sm text-muted">
        Descreva o que está acontecendo. Quanto mais detalhes, mais rápido o time consegue ajudar.
      </p>
    </header>

    <!-- #1K: chamado vinculado a um ativo (cor semântica info, NUNCA a marca — H8) -->
    <UAlert
      v-if="assetId"
      color="info"
      variant="soft"
      icon="i-lucide-server"
      title="Chamado sobre o ativo"
      :description="`Este chamado será vinculado ao ativo #${assetId}.`"
      class="mb-6"
    />

    <UCard>
      <UForm :state="form" class="space-y-6" @submit="submit">
        <!-- Seletor de contrato (condicional: só com >= 2 contratos ativos) -->
        <UFormField
          v-if="showContractSelector"
          label="Contrato"
          name="contract"
          required
          :error="contractError || undefined"
          help="A qual contrato este chamado deve ser vinculado."
        >
          <USelect
            v-model="form.contractId"
            :items="contractOptions"
            placeholder="Selecione um contrato"
            size="lg"
            class="w-full"
            icon="i-lucide-file-text"
          />
        </UFormField>

        <div v-if="serviceOptions.length || typeOptions.length" class="grid gap-5 sm:grid-cols-2">
          <UFormField v-if="serviceOptions.length" label="Serviço" name="service" help="Opcional.">
            <USelect
              v-model="form.service"
              :items="serviceOptions"
              placeholder="Selecione (opcional)"
              size="lg"
              class="w-full"
            />
          </UFormField>
          <UFormField v-if="typeOptions.length" label="Tipo" name="type" help="Opcional.">
            <USelect
              v-model="form.type"
              :items="typeOptions"
              placeholder="Selecione (opcional)"
              size="lg"
              class="w-full"
            />
          </UFormField>
        </div>

        <UFormField label="Prioridade" name="priority">
          <USelect
            v-model="form.priority"
            :items="priorityOptions"
            placeholder="Prioridade"
            size="lg"
            class="w-full"
            icon="i-lucide-flag"
          />
        </UFormField>

        <UFormField label="Assunto" name="title" required :error="titleInvalid ? 'Informe um assunto.' : undefined">
          <UInput
            v-model="form.title"
            placeholder="Ex.: Não consigo acessar o sistema"
            size="lg"
            class="w-full"
            maxlength="200"
          />
        </UFormField>

        <UFormField
          label="Descrição"
          name="body"
          required
          :error="bodyInvalid ? 'Descreva o problema.' : undefined"
          help="Conte o que aconteceu, quando começou e o impacto."
        >
          <UTextarea
            v-model="form.body"
            :rows="6"
            placeholder="Descreva o problema em detalhes…"
            size="lg"
            class="w-full"
          />
        </UFormField>

        <!-- Anexos -->
        <UFormField label="Anexos" name="files" help="Opcional. Imagens, PDF, docs e vídeos (mp4/mov/webm) · até 100 MB cada.">
          <label
            class="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-default px-4 py-5 text-sm text-muted transition hover:border-highlighted hover:text-highlighted"
          >
            <UIcon name="i-lucide-paperclip" class="h-4 w-4" />
            <span>Clique para escolher arquivos</span>
            <input
              type="file"
              multiple
              class="sr-only"
              accept=".png,.jpg,.jpeg,.pdf,.txt,.log,.csv,.zip,.doc,.docx,.mp4,.mov,.webm,.mkv,.avi"
              @change="onFilesChange"
            >
          </label>
          <ul v-if="files.length" class="mt-3 space-y-2">
            <li
              v-for="(f, idx) in files"
              :key="`${f.name}-${idx}`"
              class="flex items-center gap-2 rounded-lg border border-default bg-elevated px-3 py-2 text-sm"
            >
              <UIcon name="i-lucide-file" class="h-4 w-4 shrink-0 text-dimmed" />
              <span class="truncate text-toned">{{ f.name }}</span>
              <span class="ml-auto shrink-0 text-xs text-dimmed">{{ fmtBytes(f.size) }}</span>
              <UButton
                color="neutral"
                variant="ghost"
                size="xs"
                icon="i-lucide-x"
                :aria-label="`Remover ${f.name}`"
                @click="removeFile(idx)"
              />
            </li>
          </ul>
        </UFormField>

        <!-- Erro geral (cor semântica error, NUNCA a cor da marca — H8) -->
        <UAlert
          v-if="formError"
          color="error"
          variant="soft"
          icon="i-lucide-alert-circle"
          title="Não foi possível abrir o chamado"
          :description="formError"
        />

        <div class="flex items-center justify-end gap-3 border-t border-default pt-5">
          <UButton to="/tickets" color="neutral" variant="ghost" label="Cancelar" :disabled="submitting" />
          <UButton
            type="submit"
            color="primary"
            size="lg"
            icon="i-lucide-send"
            :loading="submitting"
            :disabled="submitting"
            label="Abrir chamado"
          />
        </div>
      </UForm>
    </UCard>
  </div>
</template>
