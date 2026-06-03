<script setup lang="ts">
definePageMeta({ middleware: 'admin-auth' })

interface UserRow {
  email: string
  first_name: string
  last_name: string
  password: string
  role: 'admin' | 'helpdesk'
}

interface OnboardingResult {
  tenant: { id: string, trade_name: string, subdomain: string }
  subdomain_to_register: string
  created_users: string[]
}

const roleOptions = [
  { label: 'Administrador', value: 'admin' },
  { label: 'Helpdesk', value: 'helpdesk' },
]

const form = reactive({
  legal_name: '',
  trade_name: '',
  document: '',
  subdomain: '',
  znuny_customer_id: '',
  branding: {
    display_name: '',
    primary_color: '#2563EB',
    accent_color: '#1E40AF',
    support_email: '',
    logo_url: '',
  },
})

const users = ref<UserRow[]>([
  { email: '', first_name: '', last_name: '', password: '', role: 'admin' },
])

function addUser() {
  users.value.push({ email: '', first_name: '', last_name: '', password: '', role: 'helpdesk' })
}
function removeUser(i: number) {
  if (users.value.length > 1) users.value.splice(i, 1)
}

const submitting = ref(false)
const errorMsg = ref('')
const result = ref<OnboardingResult | null>(null)

function validate(): string | null {
  if (!form.legal_name.trim()) return 'Razão social é obrigatória.'
  if (!form.trade_name.trim()) return 'Nome fantasia é obrigatório.'
  if (!form.document.trim()) return 'CNPJ/documento é obrigatório.'
  if (!form.subdomain.trim()) return 'Subdomínio é obrigatório.'
  if (!form.znuny_customer_id.trim()) return 'ID do cliente no Znuny é obrigatório.'
  if (!form.branding.display_name.trim()) return 'Nome de exibição (branding) é obrigatório.'
  for (const [i, u] of users.value.entries()) {
    const n = i + 1
    if (!u.email.trim()) return `Usuário ${n}: e-mail é obrigatório.`
    if (!u.first_name.trim()) return `Usuário ${n}: nome é obrigatório.`
    if (!u.last_name.trim()) return `Usuário ${n}: sobrenome é obrigatório.`
    if (!u.password.trim()) return `Usuário ${n}: senha é obrigatória.`
  }
  return null
}

async function submit() {
  errorMsg.value = ''
  const v = validate()
  if (v) { errorMsg.value = v; return }

  submitting.value = true
  try {
    const body = {
      legal_name: form.legal_name.trim(),
      trade_name: form.trade_name.trim(),
      document: form.document.trim(),
      subdomain: form.subdomain.trim(),
      znuny_customer_id: form.znuny_customer_id.trim(),
      branding: {
        display_name: form.branding.display_name.trim(),
        primary_color: form.branding.primary_color,
        accent_color: form.branding.accent_color,
        support_email: form.branding.support_email.trim() || undefined,
        logo_url: form.branding.logo_url.trim() || undefined,
      },
      users: users.value.map(u => ({
        email: u.email.trim(),
        first_name: u.first_name.trim(),
        last_name: u.last_name.trim(),
        password: u.password,
        role: u.role,
      })),
    }
    result.value = await $fetch<OnboardingResult>('/api/admin/tenants', {
      method: 'POST',
      body,
    })
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: string } }
    if (err.statusCode === 409) {
      errorMsg.value = err.data?.detail || 'Cliente já existe (subdomínio ou documento duplicado).'
    }
    else if (err.statusCode === 503) {
      errorMsg.value = err.data?.detail || 'Znuny indisponível no momento. Tente novamente.'
    }
    else {
      errorMsg.value = err.data?.detail || 'Falha ao criar o cliente. Verifique os dados e tente novamente.'
    }
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-3xl px-5 py-10">
    <div class="mb-6">
      <ULink to="/" class="inline-flex items-center gap-1 text-sm text-muted hover:text-default">
        <UIcon name="i-lucide-arrow-left" class="h-4 w-4" />
        Voltar para clientes
      </ULink>
      <h1 class="mt-2 font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Novo cliente
      </h1>
      <p class="mt-1 text-sm text-muted">
        Provisione um novo tenant: dados cadastrais, branding do portal e usuários iniciais.
      </p>
    </div>

    <!-- Sucesso -->
    <UCard v-if="result" :ui="{ body: 'space-y-5' }">
      <div class="flex items-center gap-3">
        <span class="inline-flex h-10 w-10 items-center justify-center rounded-full bg-success text-white">
          <UIcon name="i-lucide-check" class="h-5 w-5" />
        </span>
        <div>
          <p class="font-display text-lg font-bold text-highlighted">
            Cliente criado
          </p>
          <p class="text-sm text-muted">
            {{ result.tenant.trade_name }} foi provisionado.
          </p>
        </div>
      </div>

      <UAlert
        color="warning"
        variant="soft"
        icon="i-lucide-globe"
        title="Registre o DNS manualmente"
      >
        <template #description>
          O subdomínio abaixo precisa ser registrado no DNS pelo operador antes do
          cliente acessar o portal:
          <code class="mt-2 block rounded bg-muted px-3 py-2 font-mono text-sm text-highlighted">
            {{ result.subdomain_to_register }}
          </code>
        </template>
      </UAlert>

      <div v-if="result.created_users.length" class="text-sm text-muted">
        Usuários criados: {{ result.created_users.join(', ') }}
      </div>

      <div class="flex gap-3">
        <UButton :to="`/clientes/${result.tenant.id}`" color="primary" icon="i-lucide-arrow-right" trailing>
          Ver cliente
        </UButton>
        <UButton to="/" variant="ghost" color="neutral">
          Voltar à lista
        </UButton>
      </div>
    </UCard>

    <!-- Formulário -->
    <form v-else class="space-y-8" @submit.prevent="submit">
      <UAlert
        v-if="errorMsg"
        color="error"
        variant="soft"
        icon="i-lucide-alert-triangle"
        :title="errorMsg"
      />

      <section class="space-y-4">
        <h2 class="font-display text-lg font-bold text-highlighted">
          Dados cadastrais
        </h2>
        <div class="grid gap-4 sm:grid-cols-2">
          <UFormField label="Razão social" required>
            <UInput v-model="form.legal_name" placeholder="Empresa Exemplo LTDA" />
          </UFormField>
          <UFormField label="Nome fantasia" required>
            <UInput v-model="form.trade_name" placeholder="Exemplo" />
          </UFormField>
          <UFormField label="CNPJ / Documento" required>
            <UInput v-model="form.document" placeholder="00.000.000/0001-00" />
          </UFormField>
          <UFormField label="Subdomínio" required help="Ex.: exemplo (vira exemplo.suporte.gerti.com.br)">
            <UInput v-model="form.subdomain" placeholder="exemplo" />
          </UFormField>
          <UFormField label="ID do cliente no Znuny" required>
            <UInput v-model="form.znuny_customer_id" placeholder="exemplo" />
          </UFormField>
        </div>
      </section>

      <section class="space-y-4">
        <h2 class="font-display text-lg font-bold text-highlighted">
          Branding do portal
        </h2>
        <div class="grid gap-4 sm:grid-cols-2">
          <UFormField label="Nome de exibição" required>
            <UInput v-model="form.branding.display_name" placeholder="Portal Exemplo" />
          </UFormField>
          <UFormField label="E-mail de suporte">
            <UInput v-model="form.branding.support_email" type="email" placeholder="suporte@exemplo.com" />
          </UFormField>
          <UFormField label="Cor primária">
            <UInput v-model="form.branding.primary_color" type="color" />
          </UFormField>
          <UFormField label="Cor de destaque">
            <UInput v-model="form.branding.accent_color" type="color" />
          </UFormField>
          <UFormField label="URL do logo" class="sm:col-span-2">
            <UInput v-model="form.branding.logo_url" placeholder="https://..." />
          </UFormField>
        </div>
      </section>

      <section class="space-y-4">
        <div class="flex items-center justify-between">
          <h2 class="font-display text-lg font-bold text-highlighted">
            Usuários iniciais
          </h2>
          <UButton type="button" variant="soft" color="primary" icon="i-lucide-plus" size="sm" @click="addUser">
            Adicionar usuário
          </UButton>
        </div>

        <UCard
          v-for="(u, i) in users"
          :key="i"
          :ui="{ body: 'space-y-4' }"
        >
          <div class="flex items-center justify-between">
            <p class="text-sm font-semibold text-highlighted">
              Usuário {{ i + 1 }}
            </p>
            <UButton
              v-if="users.length > 1"
              type="button"
              variant="ghost"
              color="error"
              icon="i-lucide-trash-2"
              size="xs"
              @click="removeUser(i)"
            >
              Remover
            </UButton>
          </div>
          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="E-mail" required>
              <UInput v-model="u.email" type="email" placeholder="nome@exemplo.com" />
            </UFormField>
            <UFormField label="Papel" required>
              <USelect v-model="u.role" :items="roleOptions" />
            </UFormField>
            <UFormField label="Nome" required>
              <UInput v-model="u.first_name" />
            </UFormField>
            <UFormField label="Sobrenome" required>
              <UInput v-model="u.last_name" />
            </UFormField>
            <UFormField label="Senha" required class="sm:col-span-2">
              <UInput v-model="u.password" type="password" />
            </UFormField>
          </div>
        </UCard>
      </section>

      <div class="flex items-center gap-3">
        <UButton type="submit" color="primary" size="lg" :loading="submitting" icon="i-lucide-rocket">
          Criar cliente
        </UButton>
        <UButton to="/" variant="ghost" color="neutral" :disabled="submitting">
          Cancelar
        </UButton>
      </div>
    </form>
  </div>
</template>
