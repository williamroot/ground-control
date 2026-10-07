<script setup lang="ts">
// Agentes e permissões do Znuny (Spec #4, Bloco C) — capa sobre o Znuny, nada
// persistido localmente. Três ações deliberadamente separadas na UI:
//   1. Cadastro (login/nome/e-mail/validade) — NUNCA carrega senha.
//   2. Definir senha — botão próprio, modal próprio, payload só com a senha.
//   3. Permissões (grupos/papéis) — a ação mais perigosa: exige confirmação
//      explícita antes do PUT. O PUT SUBSTITUI os grupos e o sidecar não lê
//      os atuais: sem estado conhecido, a confirmação mostra com o que o
//      agente vai ficar e pede o login digitado; com estado conhecido
//      (gravado nesta sessão), mostra o diff (o que ganha, o que perde).
// O Znuny recusa (422) um agente removendo a si mesmo do grupo `admin`
// (anti-lockout do console) — avisamos ANTES de tentar e explicamos se ainda
// assim o sidecar recusar.
import {
  agentDraftFromRow,
  agentFullName,
  agentValidColor,
  agentValidLabel,
  ADMIN_GROUP_NAME,
  buildAgentProfilePayload,
  buildGroupsPayload,
  buildPasswordPayload,
  describeGroupsChange,
  diffAgentGroups,
  emptyAgentDraft,
  extractAgentError,
  extractGroupsError,
  groupIdsFromChange,
  hasGroupChanges,
  isPasswordValid,
  parseAgentList,
  parseGroupList,
  selectedGroups,
  validateAgentProfile,
  validateGroupSelection,
  validatePassword,
  wouldRemoveSelfFromAdmin,
  type AgentProfileDraft,
  type AgentRow,
} from '../../composables/useAgentGroups'

definePageMeta({ middleware: 'admin-auth' })

const headers = useRequestHeaders(['cookie'])
const toast = useToast()

const { data: session } = await useAdmin()

const { data: agentsRes, pending: agentsPending, refresh: refreshAgents } = await useAsyncData(
  'znuny-agents',
  () => $fetch<unknown>('/api/admin/znuny/agents', { headers }).catch(() => null),
)
const { data: groupsRes, pending: groupsPending, refresh: refreshGroups } = await useAsyncData(
  'znuny-groups',
  () => $fetch<unknown>('/api/admin/znuny/groups', { headers }).catch(() => null),
)

// `null` = resposta que não é lista (falha) -> estado de ERRO, nunca "vazio".
const parsedAgents = computed(() => parseAgentList(agentsRes.value))
const loadFailed = computed(() => !agentsPending.value && parsedAgents.value === null)
const agents = computed(() => parsedAgents.value ?? [])
const isEmpty = computed(() => !agentsPending.value && !loadFailed.value && agents.value.length === 0)
const groupsList = computed(() => parseGroupList(groupsRes.value))
const groupsFailed = computed(() => !groupsPending.value && !Array.isArray(groupsRes.value))

// O sidecar guarda validade como booleano: "inválido temporariamente" do
// Znuny não tem como ser escolhido por aqui.
const VALID_OPTIONS = [
  { label: 'válido', value: 'true' },
  { label: 'inválido', value: 'false' },
]

// --- Cadastro (criar/editar, sem senha) --------------------------------------
const formOpen = ref(false)
const editingAgent = ref<AgentRow | null>(null)
const isNew = computed(() => editingAgent.value === null)
const draft = reactive<AgentProfileDraft>(emptyAgentDraft())
const formError = ref('')
const submitting = ref(false)

function openCreate() {
  editingAgent.value = null
  Object.assign(draft, emptyAgentDraft())
  formError.value = ''
  formOpen.value = true
}

function openEdit(row: AgentRow) {
  editingAgent.value = row
  Object.assign(draft, agentDraftFromRow(row))
  formError.value = ''
  formOpen.value = true
}

async function submit() {
  formError.value = ''
  const errors = validateAgentProfile(draft, isNew.value)
  if (errors.length) { formError.value = errors[0]!; return }

  submitting.value = true
  try {
    const payload = buildAgentProfilePayload(draft, isNew.value)
    if (isNew.value) {
      await $fetch('/api/admin/znuny/agents', { method: 'POST', body: payload })
      toast.add({ title: 'Agente criado', color: 'success' })
    }
    else {
      await $fetch(`/api/admin/znuny/agents/${editingAgent.value!.id}`, { method: 'PUT', body: payload })
      toast.add({ title: 'Cadastro atualizado', color: 'success' })
    }
    formOpen.value = false
    await refreshAgents()
  }
  catch (e) {
    formError.value = extractAgentError(e)
  }
  finally {
    submitting.value = false
  }
}

// --- Senha (ação separada e explícita) ---------------------------------------
const pwOpen = ref(false)
const pwTarget = ref<AgentRow | null>(null)
const pwPassword = ref('')
const pwConfirm = ref('')
const pwError = ref('')
const pwSaving = ref(false)

function openPassword(row: AgentRow) {
  pwTarget.value = row
  pwPassword.value = ''
  pwConfirm.value = ''
  pwError.value = ''
  pwOpen.value = true
}

async function submitPassword() {
  if (!pwTarget.value) return
  const errors = validatePassword(pwPassword.value, pwConfirm.value)
  if (errors.length) { pwError.value = errors[0]!; return }

  pwSaving.value = true
  pwError.value = ''
  try {
    await $fetch(`/api/admin/znuny/agents/${pwTarget.value.id}/password`, {
      method: 'POST',
      body: buildPasswordPayload(pwPassword.value),
    })
    toast.add({ title: 'Senha definida', color: 'success' })
    pwOpen.value = false
  }
  catch (e) {
    pwError.value = extractAgentError(e)
  }
  finally {
    pwSaving.value = false
  }
}

// --- Permissões (grupos/papéis) — confirmação obrigatória ---------------------
// O sidecar não lê os grupos atuais de um agente e o PUT SUBSTITUI a lista.
// Grupos conhecidos = o `after` da última gravação nesta sessão; antes disso
// eles são desconhecidos, a seleção começa vazia e a confirmação exige digitar
// o login (é uma substituição às cegas do acesso de alguém).
const knownGroups = ref<Record<number, number[]>>({})
const permOpen = ref(false)
const permTarget = ref<AgentRow | null>(null)
const permStep = ref<'edit' | 'confirm'>('edit')
const currentGroupIds = ref<number[] | null>(null)
const nextGroupIds = ref<number[]>([])
const permConfirmText = ref('')
const permError = ref('')
const permSaving = ref(false)

function openPermissions(row: AgentRow) {
  permTarget.value = row
  permStep.value = 'edit'
  permError.value = ''
  permConfirmText.value = ''
  const known = knownGroups.value[row.id]
  currentGroupIds.value = known ? [...known] : null
  nextGroupIds.value = known ? [...known] : []
  permOpen.value = true
}

function toggleGroup(id: number) {
  const idx = nextGroupIds.value.indexOf(id)
  if (idx >= 0) nextGroupIds.value.splice(idx, 1)
  else nextGroupIds.value.push(id)
}

const permKnown = computed(() => currentGroupIds.value !== null)
const permDiff = computed(() =>
  diffAgentGroups(currentGroupIds.value ?? [], nextGroupIds.value, groupsList.value))
const permSelection = computed(() => selectedGroups(nextGroupIds.value, groupsList.value))
const permSelectionErrors = computed(() => validateGroupSelection(nextGroupIds.value))
const permCanReview = computed(() =>
  permSelectionErrors.value.length === 0 && (!permKnown.value || hasGroupChanges(permDiff.value)))
const permIsSelf = computed(() =>
  !!session.value && !!permTarget.value && permTarget.value.login === session.value.agent_login)
const permSelfLockout = computed(() => wouldRemoveSelfFromAdmin(
  permIsSelf.value, currentGroupIds.value, nextGroupIds.value, groupsList.value, ADMIN_GROUP_NAME))
const permConfirmOk = computed(() =>
  permKnown.value || permConfirmText.value.trim() === (permTarget.value?.login ?? ''))

function goToConfirm() {
  if (!permCanReview.value) return
  permError.value = ''
  permConfirmText.value = ''
  permStep.value = 'confirm'
}
function backToEdit() {
  permStep.value = 'edit'
}

async function confirmPermissions() {
  if (!permTarget.value || permSelfLockout.value || !permConfirmOk.value) return
  const target = permTarget.value
  permSaving.value = true
  permError.value = ''
  try {
    const change = await $fetch<unknown>(`/api/admin/znuny/agents/${target.id}/groups`, {
      method: 'PUT',
      body: buildGroupsPayload(nextGroupIds.value),
    })
    const after = groupIdsFromChange(change)
    if (after) knownGroups.value = { ...knownGroups.value, [target.id]: after }
    toast.add({
      title: `Permissões de ${target.login} atualizadas`,
      description: describeGroupsChange(change),
      color: 'success',
    })
    permOpen.value = false
  }
  catch (e) {
    permError.value = extractGroupsError(e, permSelfLockout.value)
  }
  finally {
    permSaving.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-5xl px-5 py-10">
    <header class="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
          Agentes
        </h1>
        <p class="mt-1 text-sm text-muted">
          Contas de agente do Znuny e o vínculo delas com grupos/papéis.
        </p>
      </div>
      <UButton color="primary" icon="i-lucide-user-plus" @click="openCreate">
        Novo agente
      </UButton>
    </header>

    <UAlert
      class="mb-6"
      color="warning"
      variant="soft"
      icon="i-lucide-alert-triangle"
      title="Isto edita o Znuny ao vivo"
      description="Nada é guardado pelo console. Alterar permissões afeta imediatamente o que o agente pode ver e fazer no Znuny."
    />

    <!-- Loading -->
    <div v-if="agentsPending" class="space-y-3">
      <div v-for="n in 4" :key="n" class="h-12 animate-pulse rounded-lg border border-default bg-elevated" />
    </div>

    <!-- Erro -->
    <UCard v-else-if="loadFailed" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
        <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar os agentes</p>
        <UButton variant="soft" color="primary" icon="i-lucide-refresh-cw" @click="refreshAgents()">
          Tentar novamente
        </UButton>
      </div>
    </UCard>

    <!-- Vazio -->
    <UCard v-else-if="isEmpty" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-users" class="h-10 w-10 text-muted" />
        <p class="font-display text-lg font-semibold text-highlighted">Nenhum agente cadastrado</p>
        <UButton color="primary" icon="i-lucide-user-plus" class="mt-1" @click="openCreate">
          Novo agente
        </UButton>
      </div>
    </UCard>

    <!-- Lista -->
    <div v-else class="overflow-x-auto rounded-xl border border-default">
      <table class="w-full text-sm">
        <thead class="bg-elevated text-left text-xs uppercase text-muted">
          <tr>
            <th class="px-4 py-2.5">Login</th>
            <th class="px-4 py-2.5">Nome</th>
            <th class="px-4 py-2.5">E-mail</th>
            <th class="px-4 py-2.5">Validade</th>
            <th class="px-4 py-2.5 text-right">Ações</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in agents" :key="a.id" class="border-t border-default">
            <td class="px-4 py-3 font-mono text-xs font-semibold text-highlighted">{{ a.login }}</td>
            <td class="px-4 py-3 text-default">{{ agentFullName(a) }}</td>
            <td class="px-4 py-3 text-muted">{{ a.email }}</td>
            <td class="px-4 py-3">
              <UBadge :color="agentValidColor(a.valid)" variant="soft" size="sm">
                {{ agentValidLabel(a.valid) }}
              </UBadge>
            </td>
            <td class="px-4 py-3">
              <div class="flex justify-end gap-2">
                <UButton size="xs" color="neutral" variant="soft" icon="i-lucide-pencil" @click="openEdit(a)">
                  Editar
                </UButton>
                <UButton size="xs" color="neutral" variant="soft" icon="i-lucide-key-round" @click="openPassword(a)">
                  Definir senha
                </UButton>
                <UButton size="xs" color="warning" variant="soft" icon="i-lucide-shield" @click="openPermissions(a)">
                  Permissões
                </UButton>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Modal cadastro -->
    <UModal
      v-model:open="formOpen"
      :title="isNew ? 'Novo agente' : 'Editar agente'"
      description="Cadastro do agente no Znuny. Definir senha é uma ação separada, à parte deste formulário."
      :ui="{ content: 'max-w-lg', footer: 'justify-end' }"
    >
      <template #body>
        <div class="space-y-4">
          <UAlert v-if="formError" color="error" variant="soft" icon="i-lucide-alert-triangle" :title="formError" />

          <UFormField v-if="isNew" label="Login" required help="Não pode ser alterado depois de criado.">
            <UInput v-model="draft.login" placeholder="ex.: ana.souza" class="w-full" />
          </UFormField>
          <UFormField v-else label="Login">
            <UInput :model-value="draft.login" disabled class="w-full font-mono" />
          </UFormField>

          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="Nome" required>
              <UInput v-model="draft.first_name" class="w-full" />
            </UFormField>
            <UFormField label="Sobrenome" required>
              <UInput v-model="draft.last_name" class="w-full" />
            </UFormField>
          </div>

          <UFormField label="E-mail" required>
            <UInput v-model="draft.email" type="email" class="w-full" />
          </UFormField>

          <UFormField label="Validade" required>
            <USelect v-model="draft.valid" :items="VALID_OPTIONS" class="w-full" />
          </UFormField>
        </div>
      </template>

      <template #footer>
        <UButton label="Cancelar" color="neutral" variant="ghost" :disabled="submitting" @click="formOpen = false" />
        <UButton
          :label="isNew ? 'Criar agente' : 'Salvar cadastro'"
          color="primary"
          icon="i-lucide-check"
          :loading="submitting"
          @click="submit"
        />
      </template>
    </UModal>

    <!-- Modal senha -->
    <UModal
      v-model:open="pwOpen"
      title="Definir senha"
      :ui="{ content: 'max-w-md', footer: 'justify-end' }"
    >
      <template #body>
        <div class="space-y-4">
          <UAlert
            color="warning"
            variant="soft"
            icon="i-lucide-alert-triangle"
            :title="`Isso substitui a senha de ${pwTarget?.login ?? ''} imediatamente`"
            description="Ação separada do cadastro — não afeta nome, e-mail ou permissões."
          />
          <UAlert v-if="pwError" color="error" variant="soft" icon="i-lucide-alert-triangle" :title="pwError" />

          <UFormField label="Nova senha" required>
            <UInput v-model="pwPassword" type="password" class="w-full" data-testid="new-password" />
          </UFormField>
          <UFormField label="Confirmar senha" required>
            <UInput v-model="pwConfirm" type="password" class="w-full" data-testid="confirm-password" />
          </UFormField>
        </div>
      </template>

      <template #footer>
        <UButton label="Cancelar" color="neutral" variant="ghost" :disabled="pwSaving" @click="pwOpen = false" />
        <UButton
          label="Definir senha"
          color="primary"
          icon="i-lucide-key-round"
          :loading="pwSaving"
          :disabled="!isPasswordValid(pwPassword, pwConfirm)"
          @click="submitPassword"
        />
      </template>
    </UModal>

    <!-- Modal permissões (grupos/papéis) -->
    <UModal
      v-model:open="permOpen"
      title="Permissões"
      :description="`Agente: ${permTarget?.login ?? ''}`"
      :ui="{ content: 'max-w-lg', footer: 'justify-end' }"
    >
      <template #body>
        <div v-if="groupsPending" class="h-40 animate-pulse rounded-lg bg-elevated" />

        <div v-else-if="groupsFailed" class="flex flex-col items-center gap-3 py-8 text-center">
          <UIcon name="i-lucide-alert-triangle" class="h-8 w-8 text-error" />
          <p class="text-sm text-muted">Não foi possível carregar os grupos do Znuny.</p>
          <UButton variant="soft" color="primary" icon="i-lucide-refresh-cw" @click="refreshGroups()">
            Tentar novamente
          </UButton>
        </div>

        <!-- Passo 1: escolher grupos -->
        <div v-else-if="permStep === 'edit'" class="space-y-3">
          <UAlert
            v-if="!permKnown"
            color="warning"
            variant="soft"
            icon="i-lucide-alert-triangle"
            title="Salvar substitui todos os grupos deste agente"
            description="O console ainda não consegue ler os grupos atuais de um agente. Marque TODOS os grupos que ele deve ter — o que ficar desmarcado é removido."
          />
          <p v-else class="text-sm text-muted">
            Grupos gravados nesta sessão. Marque os grupos/papéis que este agente deve ter.
          </p>
          <ul class="max-h-72 space-y-1 overflow-y-auto rounded-lg border border-default p-2">
            <li v-for="g in groupsList" :key="g.id" class="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-elevated">
              <UCheckbox
                :model-value="nextGroupIds.includes(g.id)"
                data-testid="group-checkbox"
                @update:model-value="toggleGroup(g.id)"
              />
              <span class="text-sm text-default">{{ g.name }}</span>
              <UBadge v-if="g.name.toLowerCase() === ADMIN_GROUP_NAME" color="warning" variant="soft" size="sm" class="ml-auto">
                administrador
              </UBadge>
            </li>
          </ul>
          <p v-if="permSelectionErrors.length" class="text-sm text-muted">
            {{ permSelectionErrors[0] }}
          </p>
        </div>

        <!-- Passo 2: confirmação com o diff -->
        <div v-else class="space-y-4">
          <UAlert
            color="warning"
            variant="soft"
            icon="i-lucide-shield-alert"
            title="Confirme a mudança de permissões"
            description="Esta é a ação mais sensível do console — revise o que muda antes de aplicar."
          />

          <UAlert
            v-if="permSelfLockout"
            color="error"
            variant="soft"
            icon="i-lucide-lock"
            title="Bloqueado: você ficaria sem acesso de administrador"
            description="O Znuny não permite que um agente remova a si mesmo do grupo administrador — ajuste a seleção para manter o grupo admin."
          />

          <UAlert v-if="permError" color="error" variant="soft" icon="i-lucide-alert-triangle" :title="permError" />

          <!-- Grupos atuais conhecidos: diff do que ganha e do que perde. -->
          <template v-if="permKnown">
            <div>
              <p class="mb-1 text-xs font-semibold uppercase tracking-wide text-success">Vai ganhar</p>
              <p v-if="permDiff.gained.length === 0" class="text-sm text-muted">nada</p>
              <ul v-else class="flex flex-wrap gap-1.5">
                <li v-for="g in permDiff.gained" :key="g.id">
                  <UBadge color="success" variant="soft" size="sm">{{ g.name }}</UBadge>
                </li>
              </ul>
            </div>

            <div>
              <p class="mb-1 text-xs font-semibold uppercase tracking-wide text-error">Vai perder</p>
              <p v-if="permDiff.lost.length === 0" class="text-sm text-muted">nada</p>
              <ul v-else class="flex flex-wrap gap-1.5">
                <li v-for="g in permDiff.lost" :key="g.id">
                  <UBadge color="error" variant="soft" size="sm">{{ g.name }}</UBadge>
                </li>
              </ul>
            </div>
          </template>

          <!-- Desconhecidos: mostra o estado final e pede o login digitado. -->
          <template v-else>
            <div>
              <p class="mb-1 text-xs font-semibold uppercase tracking-wide text-dimmed">
                {{ permTarget?.login }} vai ficar só com
              </p>
              <ul class="flex flex-wrap gap-1.5" data-testid="final-groups">
                <li v-for="g in permSelection" :key="g.id">
                  <UBadge color="primary" variant="soft" size="sm">{{ g.name }}</UBadge>
                </li>
              </ul>
              <p class="mt-2 text-xs text-muted">
                Qualquer outro grupo que ele tenha hoje no Znuny será removido.
              </p>
            </div>
            <UFormField :label="`Digite ${permTarget?.login ?? ''} para confirmar`">
              <UInput v-model="permConfirmText" class="w-full font-mono" autocomplete="off" />
            </UFormField>
          </template>
        </div>
      </template>

      <template #footer>
        <template v-if="permStep === 'edit'">
          <UButton label="Cancelar" color="neutral" variant="ghost" @click="permOpen = false" />
          <UButton
            label="Revisar alteração"
            color="primary"
            icon="i-lucide-arrow-right"
            :disabled="groupsPending || groupsFailed || !permCanReview"
            @click="goToConfirm"
          />
        </template>
        <template v-else>
          <UButton label="Voltar" color="neutral" variant="ghost" :disabled="permSaving" @click="backToEdit" />
          <UButton
            label="Confirmar alteração"
            color="error"
            icon="i-lucide-check"
            :loading="permSaving"
            :disabled="permSelfLockout || !permConfirmOk"
            @click="confirmPermissions"
          />
        </template>
      </template>
    </UModal>
  </div>
</template>
