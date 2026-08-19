<script setup lang="ts">
// E-mail: entrada, saída e domínios autorizados (T-R9.7, R9 do vídeo).
//
// *"Se entrou pelo suporte, tem que sair pelo suporte. Se entrou pelo
// financeiro, tem que sair pelo financeiro. Se entrou por um DPO, tem que
// voltar também pelo encarregado de dados."* (06:38)
//
// No Znuny nativo essas três configurações moram em três telas distintas, e
// ninguém consegue responder "por onde entra e por onde sai" sem abrir as três.
// A junção é o valor desta página — e é o que torna a invariante do Kleber
// verificável numa olhada.
definePageMeta({ middleware: 'admin-auth' })

interface QueueRow { ID?: number, Name?: string, SystemAddressID?: number, ValidID?: number }
interface ZnunyListResponse {
  items?: QueueRow[]
  support?: { SystemAddressList?: Record<string, string> }
}
interface TenantSummary { id: string, trade_name: string, znuny_customer_id?: string }

const headers = useRequestHeaders(['cookie'])
const toast = useToast()

const tab = ref<'entrada' | 'saida' | 'dominios'>('entrada')
const tabs = [
  { value: 'entrada', label: 'Contas de recebimento' },
  { value: 'saida', label: 'Endereços de resposta' },
  { value: 'dominios', label: 'Domínios autorizados' },
]

// ── dados ───────────────────────────────────────────────────────────────────
const { data: accounts, pending: loadingAccounts, error: accountsError, refresh: refreshAccounts }
  = await useAsyncData('znuny-mail-accounts', () =>
    $fetch<MailAccount[]>('/api/admin/znuny/mail-accounts', { headers }))

const { data: filters, pending: loadingFilters, error: filtersError, refresh: refreshFilters }
  = await useAsyncData('znuny-postmaster-filters', () =>
    $fetch<PostMasterFilter[]>('/api/admin/znuny/postmaster-filters', { headers }))

const { data: queuesRaw } = await useAsyncData('znuny-queues-for-mail', () =>
  $fetch<ZnunyListResponse>('/api/admin/znuny/objects/Queue', { headers }).catch(() => null))

const { data: tenants } = await useAsyncData('tenants-for-mail', () =>
  $fetch<TenantSummary[]>('/api/admin/tenants', { headers }).catch(() => []))

const queues = computed(() =>
  (queuesRaw.value?.items ?? [])
    .filter(q => q.ID !== undefined && q.ValidID === 1)
    .map(q => ({
      id: Number(q.ID),
      name: String(q.Name ?? q.ID),
      systemAddressId: q.SystemAddressID ? Number(q.SystemAddressID) : null,
    }))
    .sort((a, b) => a.name.localeCompare(b.name, 'pt-BR')))

const queueOptions = computed(() =>
  [{ label: '— escolha a fila —', value: 0 }, ...queues.value.map(q => ({ label: q.name, value: q.id }))])

const systemAddresses = computed(() => queuesRaw.value?.support?.SystemAddressList ?? {})
const addressLabel = (id: number | null) =>
  id ? (systemAddresses.value[String(id)] ?? `#${id}`) : '— nenhum —'

const tenantOptions = computed(() => [
  { label: '— escolha o cliente —', value: '' },
  ...(tenants.value ?? [])
    .filter(t => t.znuny_customer_id)
    .map(t => ({ label: `${t.trade_name} (${t.znuny_customer_id})`, value: t.znuny_customer_id! })),
])

// ── aba 1: contas de recebimento ────────────────────────────────────────────
const accountOpen = ref(false)
const accountDraft = reactive(emptyMailAccountDraft())
const accountErrors = ref<string[]>([])
const savingAccount = ref(false)
const accountSaveError = ref('')

function openNewAccount() {
  Object.assign(accountDraft, emptyMailAccountDraft())
  accountErrors.value = []
  accountSaveError.value = ''
  accountOpen.value = true
}
function openEditAccount(a: MailAccount) {
  Object.assign(accountDraft, draftFromAccount(a))
  accountErrors.value = []
  accountSaveError.value = ''
  accountOpen.value = true
}

async function saveAccount() {
  accountSaveError.value = ''
  accountErrors.value = validateMailAccount(accountDraft)
  if (accountErrors.value.length) return
  savingAccount.value = true
  try {
    const body = buildMailAccountPayload(accountDraft)
    if (accountDraft.id === null) {
      await $fetch('/api/admin/znuny/mail-accounts', { method: 'POST', body })
    }
    else {
      await $fetch(`/api/admin/znuny/mail-accounts/${accountDraft.id}`, { method: 'PUT', body })
    }
    accountOpen.value = false
    await refreshAccounts()
    toast.add({ title: 'Conta salva', color: 'success' })
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: string } }
    accountSaveError.value = err.statusCode === 503
      ? 'Znuny indisponível — nada foi salvo.'
      : (err.data?.detail || 'Falha ao salvar a conta.')
  }
  finally {
    savingAccount.value = false
  }
}

// ── aba 3: domínios autorizados ─────────────────────────────────────────────
const domainOpen = ref(false)
const domainDraft = reactive<DomainRuleDraft>({
  name: '', domain: '', customer_id: '', queue_name: '', stop_after_match: false,
})
const domainEditing = ref<string | null>(null)
const domainErrors = ref<string[]>([])
const savingDomain = ref(false)
const domainSaveError = ref('')

function openNewDomain() {
  Object.assign(domainDraft, {
    name: '', domain: '', customer_id: '', queue_name: '', stop_after_match: false,
  })
  domainEditing.value = null
  domainErrors.value = []
  domainSaveError.value = ''
  domainOpen.value = true
}

function openEditDomain(f: PostMasterFilter) {
  Object.assign(domainDraft, {
    name: f.name,
    domain: domainOfFilter(f) ?? '',
    customer_id: customerOfFilter(f) ?? '',
    queue_name: f.set.find(p => p.key === 'X-OTRS-Queue')?.value ?? '',
    stop_after_match: f.stop_after_match,
  })
  domainEditing.value = f.name
  domainErrors.value = []
  domainSaveError.value = ''
  domainOpen.value = true
}

async function saveDomain() {
  domainSaveError.value = ''
  domainErrors.value = validateDomainRule(domainDraft)
  if (domainErrors.value.length) return
  savingDomain.value = true
  try {
    const body = buildDomainRulePayload(domainDraft)
    if (domainEditing.value) {
      await $fetch(`/api/admin/znuny/postmaster-filters/${encodeURIComponent(domainEditing.value)}`,
        { method: 'PUT', body })
    }
    else {
      await $fetch('/api/admin/znuny/postmaster-filters', { method: 'POST', body })
    }
    domainOpen.value = false
    await refreshFilters()
    toast.add({ title: 'Regra salva', color: 'success' })
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: string } }
    domainSaveError.value = err.data?.detail || 'Falha ao salvar a regra.'
  }
  finally {
    savingDomain.value = false
  }
}

// Remover é o ÚNICO caminho de exclusão real da capa de administração — o
// filtro não tem "invalidar". Por isso a confirmação exige o nome digitado.
const removeTarget = ref<PostMasterFilter | null>(null)
const removeTyped = ref('')
const removing = ref(false)
const removeReady = computed(() =>
  !!removeTarget.value && removeTyped.value.trim() === removeTarget.value.name)

async function confirmRemove() {
  if (!removeReady.value || !removeTarget.value) return
  removing.value = true
  try {
    await $fetch(`/api/admin/znuny/postmaster-filters/${encodeURIComponent(removeTarget.value.name)}`,
      { method: 'DELETE' })
    removeTarget.value = null
    await refreshFilters()
    toast.add({ title: 'Regra removida', color: 'success' })
  }
  finally {
    removing.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-6xl px-5 py-10">
    <header class="mb-6">
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        E-mail
      </h1>
      <p class="mt-1 text-sm text-muted">
        Por onde o chamado entra, por onde a resposta sai, e de quem é cada domínio.
      </p>
    </header>

    <UTabs v-model="tab" :items="tabs" class="mb-6" />

    <!-- ── entrada ─────────────────────────────────────────────────────── -->
    <section v-if="tab === 'entrada'">
      <div class="mb-4 flex items-center justify-between">
        <p class="text-sm text-muted">
          Cada caixa de recebimento entrega as mensagens numa fila.
        </p>
        <UButton color="primary" icon="i-lucide-plus" @click="openNewAccount">
          Nova conta
        </UButton>
      </div>

      <UCard v-if="loadingAccounts" class="text-sm text-muted">
        Carregando contas…
      </UCard>
      <UCard v-else-if="accountsError" class="text-center">
        <div class="flex flex-col items-center gap-3 py-10">
          <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
          <p class="font-display text-lg font-semibold text-highlighted">
            Falha ao ler as contas no Znuny
          </p>
          <UButton variant="soft" color="primary" @click="refreshAccounts()">
            Tentar de novo
          </UButton>
        </div>
      </UCard>
      <UCard v-else-if="!accounts?.length" class="text-center">
        <div class="flex flex-col items-center gap-3 py-10">
          <UIcon name="i-lucide-inbox" class="h-10 w-10 text-muted" />
          <p class="font-display text-lg font-semibold text-highlighted">
            Nenhuma conta de recebimento
          </p>
          <p class="max-w-md text-sm text-muted">
            Enquanto não houver uma caixa cadastrada, nenhum chamado entra por e-mail.
          </p>
          <UButton color="primary" icon="i-lucide-plus" @click="openNewAccount">
            Cadastrar a primeira
          </UButton>
        </div>
      </UCard>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-default text-left text-muted">
              <th class="py-2 pr-3 font-medium">Caixa</th>
              <th class="py-2 pr-3 font-medium">Servidor</th>
              <th class="py-2 pr-3 font-medium">Entrega na fila</th>
              <th class="py-2 pr-3 font-medium">Estado</th>
              <th class="py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in accounts" :key="a.id" class="border-b border-default/60">
              <td class="py-3 pr-3">
                <p class="font-medium text-highlighted">{{ a.login }}</p>
                <p class="text-xs text-muted">{{ a.type }}</p>
              </td>
              <td class="py-3 pr-3 text-default">{{ a.host }}</td>
              <td class="py-3 pr-3">
                <UBadge v-if="a.queue_name" color="primary" variant="subtle" size="sm">
                  {{ a.queue_name }}
                </UBadge>
                <span v-else class="text-muted">por remetente</span>
              </td>
              <td class="py-3 pr-3">
                <UBadge :color="a.valid ? 'success' : 'neutral'" variant="soft" size="sm">
                  {{ a.valid ? 'Ativa' : 'Inativa' }}
                </UBadge>
              </td>
              <td class="py-3 text-right">
                <UButton size="xs" variant="ghost" color="neutral" icon="i-lucide-pencil" @click="openEditAccount(a)">
                  Editar
                </UButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- ── saída ───────────────────────────────────────────────────────── -->
    <section v-else-if="tab === 'saida'">
      <UAlert
        class="mb-4"
        color="warning"
        variant="soft"
        icon="i-lucide-corner-up-left"
        title="Como o Znuny escolhe o remetente da resposta"
        :description="OUTBOUND_WARNING"
      />
      <p class="mb-3 text-sm text-muted">
        O endereço de resposta é atributo da fila. Para trocá-lo, edite a fila em
        <ULink to="/znuny/filas" class="text-primary">Filas</ULink>.
      </p>
      <UCard v-if="!queues.length" class="text-sm text-muted">
        Nenhuma fila cadastrada.
      </UCard>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-default text-left text-muted">
              <th class="py-2 pr-3 font-medium">Fila</th>
              <th class="py-2 pr-3 font-medium">Responde por</th>
              <th class="py-2 font-medium">Recebe de</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="q in queues" :key="q.id" class="border-b border-default/60">
              <td class="py-3 pr-3 font-medium text-highlighted">{{ q.name }}</td>
              <td class="py-3 pr-3 text-default">{{ addressLabel(q.systemAddressId) }}</td>
              <td class="py-3">
                <span v-if="(accounts ?? []).some(a => a.queue_id === q.id)" class="text-default">
                  {{ (accounts ?? []).filter(a => a.queue_id === q.id).map(a => a.login).join(', ') }}
                </span>
                <span v-else class="text-muted">— nenhuma caixa —</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- ── domínios ────────────────────────────────────────────────────── -->
    <section v-else>
      <div class="mb-4 flex items-center justify-between">
        <p class="text-sm text-muted">
          De quem é cada domínio de remetente — a visão de todos os clientes numa tela.
        </p>
        <UButton color="primary" icon="i-lucide-plus" @click="openNewDomain">
          Nova regra
        </UButton>
      </div>

      <UCard v-if="loadingFilters" class="text-sm text-muted">
        Carregando regras…
      </UCard>
      <UCard v-else-if="filtersError" class="text-center">
        <div class="flex flex-col items-center gap-3 py-10">
          <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
          <p class="font-display text-lg font-semibold text-highlighted">
            Falha ao ler as regras no Znuny
          </p>
          <UButton variant="soft" color="primary" @click="refreshFilters()">
            Tentar de novo
          </UButton>
        </div>
      </UCard>
      <UCard v-else-if="!filters?.length" class="text-center">
        <div class="flex flex-col items-center gap-3 py-10">
          <UIcon name="i-lucide-at-sign" class="h-10 w-10 text-muted" />
          <p class="font-display text-lg font-semibold text-highlighted">
            Nenhum domínio autorizado
          </p>
          <p class="max-w-md text-sm text-muted">
            Sem regra, um e-mail de remetente desconhecido entra sem cliente associado.
          </p>
          <UButton color="primary" icon="i-lucide-plus" @click="openNewDomain">
            Cadastrar a primeira
          </UButton>
        </div>
      </UCard>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-default text-left text-muted">
              <th class="py-2 pr-3 font-medium">Regra</th>
              <th class="py-2 pr-3 font-medium">Domínio</th>
              <th class="py-2 pr-3 font-medium">Cliente</th>
              <th class="py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in filters" :key="f.name" class="border-b border-default/60">
              <td class="py-3 pr-3 font-medium text-highlighted">{{ f.name }}</td>
              <td class="py-3 pr-3 font-mono text-xs text-default">
                {{ domainOfFilter(f) ?? '—' }}
              </td>
              <td class="py-3 pr-3">
                <UBadge v-if="customerOfFilter(f)" color="primary" variant="subtle" size="sm">
                  {{ customerOfFilter(f) }}
                </UBadge>
                <span v-else class="text-muted">— não atribui —</span>
              </td>
              <td class="py-3 text-right">
                <div class="flex justify-end gap-1">
                  <UButton size="xs" variant="ghost" color="neutral" icon="i-lucide-pencil" @click="openEditDomain(f)">
                    Editar
                  </UButton>
                  <UButton
                    size="xs"
                    variant="ghost"
                    color="error"
                    icon="i-lucide-trash-2"
                    @click="removeTarget = f; removeTyped = ''"
                  >
                    Remover
                  </UButton>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- conta -->
    <UModal v-model:open="accountOpen" :title="accountDraft.id === null ? 'Nova conta de recebimento' : 'Editar conta'">
      <template #body>
        <div class="space-y-4">
          <UAlert
            v-if="accountErrors.length"
            color="error"
            variant="soft"
            icon="i-lucide-alert-triangle"
            title="Corrija os itens abaixo"
          >
            <template #description>
              <ul class="list-disc space-y-0.5 pl-5">
                <li v-for="e in accountErrors" :key="e">{{ e }}</li>
              </ul>
            </template>
          </UAlert>
          <UAlert v-if="accountSaveError" color="error" variant="soft" icon="i-lucide-alert-triangle" :title="accountSaveError" />

          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="Usuário da caixa" required>
              <UInput v-model="accountDraft.login" placeholder="suporte@gerti.com.br" />
            </UFormField>
            <UFormField label="Servidor" required>
              <UInput v-model="accountDraft.host" placeholder="imap.gerti.com.br" />
            </UFormField>
            <UFormField label="Protocolo" required>
              <USelect v-model="accountDraft.type" :items="MAIL_ACCOUNT_TYPES.map(t => ({ label: t, value: t }))" />
            </UFormField>
            <UFormField label="Pasta (IMAP)">
              <UInput v-model="accountDraft.imap_folder" placeholder="INBOX" />
            </UFormField>
            <UFormField
              label="Senha"
              class="sm:col-span-2"
              help="O sistema nunca devolve a senha guardada. Deixe em branco para mantê-la."
            >
              <UInput v-model="accountDraft.password" type="password" :placeholder="passwordPlaceholder(accountDraft)" />
            </UFormField>
            <UFormField label="Entrega na fila" required class="sm:col-span-2">
              <USelect v-model="accountDraft.queue_id" :items="queueOptions" />
            </UFormField>
            <UFormField class="sm:col-span-2">
              <UCheckbox v-model="accountDraft.valid" label="Conta ativa (o daemon busca mensagens dela)" />
            </UFormField>
          </div>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <UButton variant="ghost" color="neutral" :disabled="savingAccount" @click="accountOpen = false">
            Cancelar
          </UButton>
          <UButton color="primary" :loading="savingAccount" @click="saveAccount">
            Salvar
          </UButton>
        </div>
      </template>
    </UModal>

    <!-- domínio -->
    <UModal v-model:open="domainOpen" :title="domainEditing ? 'Editar regra de domínio' : 'Nova regra de domínio'">
      <template #body>
        <div class="space-y-4">
          <UAlert
            v-if="domainErrors.length"
            color="error"
            variant="soft"
            icon="i-lucide-alert-triangle"
            title="Corrija os itens abaixo"
          >
            <template #description>
              <ul class="list-disc space-y-0.5 pl-5">
                <li v-for="e in domainErrors" :key="e">{{ e }}</li>
              </ul>
            </template>
          </UAlert>
          <UAlert v-if="domainSaveError" color="error" variant="soft" icon="i-lucide-alert-triangle" :title="domainSaveError" />

          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="Nome da regra" required class="sm:col-span-2">
              <UInput v-model="domainDraft.name" placeholder="aurora-dominio" :disabled="!!domainEditing" />
            </UFormField>
            <UFormField label="Domínio do remetente" required>
              <UInput v-model="domainDraft.domain" placeholder="auroramoveis.com.br" />
            </UFormField>
            <UFormField label="Cliente" required>
              <USelect v-model="domainDraft.customer_id" :items="tenantOptions" />
            </UFormField>
            <UFormField label="Fila (opcional)" class="sm:col-span-2" help="Deixe vazio para usar a fila da caixa de recebimento.">
              <UInput v-model="domainDraft.queue_name" placeholder="Suporte::N1" />
            </UFormField>
          </div>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <UButton variant="ghost" color="neutral" :disabled="savingDomain" @click="domainOpen = false">
            Cancelar
          </UButton>
          <UButton color="primary" :loading="savingDomain" @click="saveDomain">
            Salvar
          </UButton>
        </div>
      </template>
    </UModal>

    <!-- remover regra -->
    <UModal
      :open="removeTarget !== null"
      title="Remover regra de domínio"
      @update:open="(v: boolean) => { if (!v) removeTarget = null }"
    >
      <template #body>
        <div class="space-y-4">
          <UAlert
            color="warning"
            variant="soft"
            icon="i-lucide-alert-triangle"
            title="Esta é a única exclusão real do console"
            description="Filtro de e-mail não tem 'invalidar' no Znuny — ele é apagado de verdade. O estado anterior fica registrado na auditoria."
          />
          <UFormField label="Digite o nome da regra para confirmar">
            <UInput v-model="removeTyped" :placeholder="removeTarget?.name" />
          </UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <UButton variant="ghost" color="neutral" :disabled="removing" @click="removeTarget = null">
            Cancelar
          </UButton>
          <UButton color="error" :disabled="!removeReady" :loading="removing" @click="confirmRemove">
            Remover
          </UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
