<script setup lang="ts">
// Usuários do cliente (T-R2.5, R2 do vídeo — o requisito mais importante).
//
// Um único formulário por pessoa, dizendo com todas as letras que o cadastro
// serve para o portal E para o e-mail. É o diferencial que se demonstra: no
// TIFLUX são dois cadastros, e o chamado que entra por e-mail nunca chega ao
// portal de quem o mandou.
//
// Desativar é ValidID=2 no Znuny — nunca exclusão (invariante 3) — e por ser
// ação de risco exige o e-mail digitado.
definePageMeta({ middleware: 'admin-auth' })

interface TenantHeader { id: string, trade_name: string, subdomain: string }
interface UsersResponse { users: TenantUser[], degraded: boolean, truncated: boolean }

const route = useRoute()
const id = route.params.id as string
const headers = useRequestHeaders(['cookie'])

const { data: tenant } = await useAsyncData(`admin-tenant-head-${id}`, () =>
  $fetch<TenantHeader | null>(`/api/admin/tenants/${id}`, { headers }).catch(() => null))

const { data, pending, error, refresh } = await useAsyncData(`admin-tenant-users-${id}`, () =>
  $fetch<UsersResponse>(`/api/admin/tenants/${id}/users`, { headers }))

const users = computed(() => data.value?.users ?? [])
const degraded = computed(() => data.value?.degraded === true)
const truncated = computed(() => data.value?.truncated === true)

const roleOptions = [
  { label: 'Administrador', value: 'admin' },
  { label: 'Helpdesk', value: 'helpdesk' },
]

const open = ref(false)
const editingLogin = ref<string | null>(null)
const draft = reactive(emptyUserDraft())
const formErrors = ref<string[]>([])
const saving = ref(false)
const saveError = ref('')

const isEdit = computed(() => editingLogin.value !== null)

function openCreate() {
  Object.assign(draft, emptyUserDraft())
  editingLogin.value = null
  formErrors.value = []
  saveError.value = ''
  open.value = true
}

function openEdit(u: TenantUser) {
  Object.assign(draft, draftFromUser(u))
  editingLogin.value = u.customer_login
  formErrors.value = []
  saveError.value = ''
  open.value = true
}

async function save() {
  saveError.value = ''
  formErrors.value = validateUserDraft(draft, { isEdit: isEdit.value })
  if (formErrors.value.length) return

  saving.value = true
  try {
    if (isEdit.value) {
      await $fetch(`/api/admin/tenants/${id}/users/${encodeURIComponent(editingLogin.value!)}`, {
        method: 'PUT',
        body: buildUpdatePayload(draft),
      })
    }
    else {
      await $fetch(`/api/admin/tenants/${id}/users`, {
        method: 'POST',
        body: buildCreatePayload(draft),
      })
    }
    open.value = false
    await refresh()
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: string } }
    if (err.statusCode === 409) saveError.value = err.data?.detail || 'Znuny recusou a gravação.'
    else if (err.statusCode === 503) saveError.value = 'Znuny indisponível — nada foi alterado.'
    else if (err.statusCode === 404) saveError.value = 'Usuário não encontrado neste cliente.'
    else saveError.value = err.data?.detail || 'Falha ao salvar. Tente novamente.'
  }
  finally {
    saving.value = false
  }
}

// ── Desativação (destrutiva o bastante para exigir confirmação digitada) ────
const deactivateOpen = ref(false)
const deactivateTarget = ref<TenantUser | null>(null)
const deactivateTyped = ref('')
const deactivating = ref(false)
const deactivateError = ref('')

const deactivateReady = computed(() =>
  !!deactivateTarget.value
  && confirmDeactivateMatches(deactivateTyped.value, deactivateTarget.value.customer_login))

function askDeactivate(u: TenantUser) {
  deactivateTarget.value = u
  deactivateTyped.value = ''
  deactivateError.value = ''
  deactivateOpen.value = true
}

async function confirmDeactivate() {
  if (!deactivateReady.value || !deactivateTarget.value) return
  deactivating.value = true
  deactivateError.value = ''
  try {
    const login = deactivateTarget.value.customer_login
    await $fetch(`/api/admin/tenants/${id}/users/${encodeURIComponent(login)}`, {
      method: 'PUT',
      body: { active: false },
    })
    deactivateOpen.value = false
    await refresh()
  }
  catch (e) {
    const err = e as { data?: { detail?: string } }
    deactivateError.value = err.data?.detail || 'Falha ao desativar. Tente novamente.'
  }
  finally {
    deactivating.value = false
  }
}

async function reactivate(u: TenantUser) {
  await $fetch(`/api/admin/tenants/${id}/users/${encodeURIComponent(u.customer_login)}`, {
    method: 'PUT',
    body: { active: true },
  })
  await refresh()
}

const roleLabel = (r: string | null) =>
  r === 'admin' ? 'Administrador' : r === 'helpdesk' ? 'Helpdesk' : '—'
</script>

<template>
  <div class="mx-auto max-w-5xl px-5 py-10">
    <ULink :to="`/clientes/${id}`" class="inline-flex items-center gap-1 text-sm text-muted hover:text-default">
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" />
      Voltar para o cliente
    </ULink>

    <header class="mt-3 mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
          Usuários
        </h1>
        <p class="mt-1 text-sm text-muted">
          {{ tenant?.trade_name ?? 'Cliente' }}
        </p>
      </div>
      <UButton color="primary" icon="i-lucide-user-plus" @click="openCreate">
        Adicionar usuário
      </UButton>
    </header>

    <UAlert
      class="mb-4"
      color="info"
      variant="soft"
      icon="i-lucide-info"
      :title="CADASTRO_UNICO_HINT"
    />

    <UAlert
      v-if="degraded"
      class="mb-4"
      color="warning"
      variant="soft"
      icon="i-lucide-plug-zap"
      title="Znuny indisponível — lista incompleta"
      description="Estamos mostrando apenas quem tem acesso ao portal registrado aqui. Pessoas cadastradas só no Znuny não aparecem enquanto a conexão não voltar."
    />

    <UAlert
      v-if="truncated"
      class="mb-4"
      color="warning"
      variant="soft"
      icon="i-lucide-list-filter"
      title="Lista cortada"
      description="Este cliente tem mais pessoas do que a listagem devolve de uma vez. Quem não aparece aqui continua cadastrado — nada foi removido."
    />

    <UCard v-if="pending" class="text-sm text-muted">
      Carregando usuários…
    </UCard>

    <UCard v-else-if="error" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
        <p class="font-display text-lg font-semibold text-highlighted">
          Falha ao carregar os usuários
        </p>
        <UButton variant="soft" color="primary" @click="refresh()">
          Tentar de novo
        </UButton>
      </div>
    </UCard>

    <UCard v-else-if="users.length === 0" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-users" class="h-10 w-10 text-muted" />
        <p class="font-display text-lg font-semibold text-highlighted">
          Nenhum usuário ainda
        </p>
        <p class="max-w-md text-sm text-muted">
          Cadastre a primeira pessoa deste cliente. Ela poderá abrir chamados pelo
          portal e por e-mail com o mesmo cadastro.
        </p>
        <UButton color="primary" icon="i-lucide-user-plus" @click="openCreate">
          Adicionar usuário
        </UButton>
      </div>
    </UCard>

    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-default text-left text-muted">
            <th class="py-2 pr-3 font-medium">Pessoa</th>
            <th class="py-2 pr-3 font-medium">Contato</th>
            <th class="py-2 pr-3 font-medium">Papel</th>
            <th class="py-2 pr-3 font-medium">E-mail</th>
            <th class="py-2 pr-3 font-medium">Estado</th>
            <th class="py-2 font-medium" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.customer_login" class="border-b border-default/60">
            <td class="py-3 pr-3">
              <p class="font-medium text-highlighted">
                {{ [u.first_name, u.last_name].filter(Boolean).join(' ') || u.customer_login }}
              </p>
              <p class="text-xs text-muted">{{ u.customer_login }}</p>
            </td>
            <td class="py-3 pr-3 text-default">
              <p v-if="u.phone">{{ u.phone }}</p>
              <p v-if="u.extension" class="text-xs text-muted">Ramal {{ u.extension }}</p>
              <span v-if="!u.phone && !u.extension" class="text-muted">—</span>
            </td>
            <td class="py-3 pr-3">
              <UBadge v-if="u.role" color="primary" variant="subtle" size="sm">
                {{ roleLabel(u.role) }}
              </UBadge>
              <span v-else class="text-muted">—</span>
            </td>
            <td class="py-3 pr-3">
              <UBadge
                :color="u.email_intake_enabled ? 'success' : 'neutral'"
                variant="subtle"
                size="sm"
              >
                {{ u.email_intake_enabled ? 'Libera' : 'Bloqueado' }}
              </UBadge>
            </td>
            <td class="py-3 pr-3">
              <UBadge
                :color="!u.active ? 'neutral' : u.has_portal_access ? 'success' : 'warning'"
                variant="soft"
                size="sm"
              >
                {{ userStatusLabel(u) }}
              </UBadge>
            </td>
            <td class="py-3 text-right">
              <div class="flex justify-end gap-1">
                <UButton size="xs" variant="ghost" color="neutral" icon="i-lucide-pencil" @click="openEdit(u)">
                  Editar
                </UButton>
                <UButton
                  v-if="u.active"
                  size="xs"
                  variant="ghost"
                  color="error"
                  icon="i-lucide-user-minus"
                  @click="askDeactivate(u)"
                >
                  Desativar
                </UButton>
                <UButton
                  v-else
                  size="xs"
                  variant="ghost"
                  color="success"
                  icon="i-lucide-user-check"
                  @click="reactivate(u)"
                >
                  Reativar
                </UButton>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Criar / editar -->
    <UModal v-model:open="open" :title="isEdit ? 'Editar usuário' : 'Novo usuário'">
      <template #body>
        <div class="space-y-4">
          <UAlert color="info" variant="soft" icon="i-lucide-info" :title="CADASTRO_UNICO_HINT" />
          <UAlert
            v-if="formErrors.length"
            color="error"
            variant="soft"
            icon="i-lucide-alert-triangle"
            title="Corrija os itens abaixo"
          >
            <template #description>
              <ul class="list-disc space-y-0.5 pl-5">
                <li v-for="e in formErrors" :key="e">{{ e }}</li>
              </ul>
            </template>
          </UAlert>
          <UAlert
            v-if="saveError"
            color="error"
            variant="soft"
            icon="i-lucide-alert-triangle"
            :title="saveError"
          />

          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="E-mail" required class="sm:col-span-2">
              <UInput v-model="draft.email" type="email" />
            </UFormField>
            <UFormField label="Nome" :required="!isEdit">
              <UInput v-model="draft.first_name" />
            </UFormField>
            <UFormField label="Sobrenome" :required="!isEdit">
              <UInput v-model="draft.last_name" />
            </UFormField>
            <UFormField label="Telefone">
              <UInput v-model="draft.phone" />
            </UFormField>
            <UFormField label="Celular">
              <UInput v-model="draft.mobile" />
            </UFormField>
            <UFormField label="Ramal" help="Guardado no Ground Control — o Znuny não tem esse campo.">
              <UInput v-model="draft.extension" />
            </UFormField>
            <UFormField label="Papel no portal" required>
              <USelect v-model="draft.role" :items="roleOptions" />
            </UFormField>
            <UFormField v-if="!isEdit" label="Senha" required class="sm:col-span-2">
              <UInput v-model="draft.password" type="password" />
            </UFormField>
            <UFormField class="sm:col-span-2">
              <UCheckbox
                v-model="draft.email_intake_enabled"
                label="Libera abertura de chamado por e-mail"
              />
            </UFormField>
          </div>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <UButton variant="ghost" color="neutral" :disabled="saving" @click="open = false">
            Cancelar
          </UButton>
          <UButton color="primary" :loading="saving" @click="save">
            {{ isEdit ? 'Salvar' : 'Cadastrar' }}
          </UButton>
        </div>
      </template>
    </UModal>

    <!-- Desativar -->
    <UModal v-model:open="deactivateOpen" title="Desativar usuário">
      <template #body>
        <div class="space-y-4">
          <p class="text-sm text-default">
            <strong>{{ deactivateTarget?.customer_login }}</strong> perderá o acesso ao portal e
            deixará de abrir chamados por e-mail. O cadastro <strong>não é apagado</strong> —
            fica inválido no Znuny e pode ser reativado.
          </p>
          <UFormField label="Digite o e-mail para confirmar">
            <UInput v-model="deactivateTyped" :placeholder="deactivateTarget?.customer_login" />
          </UFormField>
          <UAlert
            v-if="deactivateError"
            color="error"
            variant="soft"
            icon="i-lucide-alert-triangle"
            :title="deactivateError"
          />
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <UButton variant="ghost" color="neutral" :disabled="deactivating" @click="deactivateOpen = false">
            Cancelar
          </UButton>
          <UButton
            color="error"
            :disabled="!deactivateReady"
            :loading="deactivating"
            @click="confirmDeactivate"
          >
            Desativar
          </UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
