<script setup lang="ts">
// Assistente de cadastro de cliente em 3 etapas (T-R1.4, R1 do vídeo).
// A validação por etapa vive em `useTenantWizard` (lógica pura, testada
// isoladamente); aqui só tem tela. Ao final, cai na ficha do cliente — que é
// onde o Kleber espera cair ("uma telinha de edição", 01:10).
definePageMeta({ middleware: 'admin-auth' })

interface OnboardingResult {
  tenant: { id: string, trade_name: string, subdomain: string }
  subdomain_to_register: string
  created_users: string[]
}

const roleOptions = [
  { label: 'Administrador', value: 'admin' },
  { label: 'Helpdesk', value: 'helpdesk' },
]

const draft = reactive(emptyTenantWizardDraft())
const step = ref<WizardStep>(1)
const submitting = ref(false)
const errorMsg = ref('')
const stepErrors = ref<string[]>([])
const result = ref<OnboardingResult | null>(null)

const steps: WizardStep[] = [1, 2, 3]

function addUser() {
  draft.users.push(emptyTenantUser('helpdesk'))
}
function removeUser(i: number) {
  if (draft.users.length > 1) draft.users.splice(i, 1)
}

function next() {
  const errors = validateStep(step.value, draft)
  stepErrors.value = errors
  if (errors.length) return
  if (step.value < 3) step.value = (step.value + 1) as WizardStep
}

function back() {
  stepErrors.value = []
  if (step.value > 1) step.value = (step.value - 1) as WizardStep
}

// Voltar a uma etapa já vencida é livre; pular para a frente exige que as
// anteriores estejam válidas — senão o assistente não estaria validando nada.
function goTo(target: WizardStep) {
  if (target <= step.value) { step.value = target; stepErrors.value = []; return }
  for (const s of steps) {
    if (s >= target) break
    const errors = validateStep(s, draft)
    if (errors.length) { step.value = s; stepErrors.value = errors; return }
  }
  step.value = target
  stepErrors.value = []
}

function onZipBlur() {
  draft.address_zip = normalizeZip(draft.address_zip)
}
function onStateBlur() {
  draft.address_state = normalizeState(draft.address_state)
}

async function submit() {
  errorMsg.value = ''
  // Revalida TODAS as etapas: o operador pode ter voltado e esvaziado um campo.
  for (const s of steps) {
    const errors = validateStep(s, draft)
    if (errors.length) { step.value = s; stepErrors.value = errors; return }
  }
  stepErrors.value = []

  submitting.value = true
  try {
    result.value = await $fetch<OnboardingResult>('/api/admin/tenants', {
      method: 'POST',
      body: buildTenantBody(draft),
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
        Provisione um novo tenant: dados cadastrais, identidade visual do portal e usuários.
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

    <template v-else>
      <!-- Trilha das etapas -->
      <ol class="mb-8 flex items-center gap-2" aria-label="Etapas do cadastro">
        <li v-for="(s, i) in steps" :key="s" class="flex flex-1 items-center gap-2">
          <button
            type="button"
            class="flex items-center gap-2 text-left"
            :aria-current="s === step ? 'step' : undefined"
            @click="goTo(s)"
          >
            <span
              class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold"
              :class="s === step
                ? 'bg-primary text-inverted'
                : s < step ? 'bg-success text-white' : 'bg-elevated text-muted'"
            >
              <UIcon v-if="s < step" name="i-lucide-check" class="h-4 w-4" />
              <template v-else>{{ s }}</template>
            </span>
            <span
              class="hidden text-sm sm:inline"
              :class="s === step ? 'font-semibold text-highlighted' : 'text-muted'"
            >{{ STEP_TITLES[s] }}</span>
          </button>
          <span v-if="i < steps.length - 1" class="h-px flex-1 bg-accented" />
        </li>
      </ol>

      <form class="space-y-8" @submit.prevent="submit">
        <UAlert
          v-if="errorMsg"
          color="error"
          variant="soft"
          icon="i-lucide-alert-triangle"
          :title="errorMsg"
        />
        <UAlert
          v-if="stepErrors.length"
          color="error"
          variant="soft"
          icon="i-lucide-alert-triangle"
          :title="stepErrors.length === 1 ? 'Corrija antes de avançar' : 'Corrija os itens abaixo'"
        >
          <template #description>
            <ul class="list-disc space-y-0.5 pl-5">
              <li v-for="e in stepErrors" :key="e">
                {{ e }}
              </li>
            </ul>
          </template>
        </UAlert>

        <!-- Etapa 1 — dados cadastrais, endereço e contato -->
        <section v-show="step === 1" class="space-y-6">
          <div class="space-y-4">
            <h2 class="font-display text-lg font-bold text-highlighted">
              Dados cadastrais
            </h2>
            <div class="grid gap-4 sm:grid-cols-2">
              <UFormField label="Razão social" required>
                <UInput v-model="draft.legal_name" placeholder="Empresa Exemplo LTDA" />
              </UFormField>
              <UFormField label="Nome fantasia" required>
                <UInput v-model="draft.trade_name" placeholder="Exemplo" />
              </UFormField>
              <UFormField label="CNPJ / Documento" required>
                <UInput v-model="draft.document" placeholder="00.000.000/0001-00" />
              </UFormField>
              <UFormField
                label="Subdomínio"
                required
                help="Não pode ser alterado depois de criado."
              >
                <UInput v-model="draft.subdomain" placeholder="exemplo" />
              </UFormField>
              <UFormField
                label="ID do cliente no Znuny"
                required
                help="Não pode ser alterado depois de criado."
              >
                <UInput v-model="draft.znuny_customer_id" placeholder="EXEMPLO" />
              </UFormField>
            </div>
          </div>

          <div class="space-y-4">
            <h2 class="font-display text-lg font-bold text-highlighted">
              Endereço
            </h2>
            <div class="grid gap-4 sm:grid-cols-6">
              <UFormField label="Logradouro" class="sm:col-span-4">
                <UInput v-model="draft.address_street" placeholder="Rua das Acácias" />
              </UFormField>
              <UFormField label="Número" class="sm:col-span-2">
                <UInput v-model="draft.address_number" placeholder="100" />
              </UFormField>
              <UFormField label="Complemento" class="sm:col-span-3">
                <UInput v-model="draft.address_complement" placeholder="Sala 302" />
              </UFormField>
              <UFormField label="Bairro" class="sm:col-span-3">
                <UInput v-model="draft.address_district" placeholder="Centro" />
              </UFormField>
              <UFormField label="Cidade" class="sm:col-span-3">
                <UInput v-model="draft.address_city" placeholder="Belo Horizonte" />
              </UFormField>
              <UFormField label="UF" class="sm:col-span-1">
                <UInput v-model="draft.address_state" placeholder="MG" @blur="onStateBlur" />
              </UFormField>
              <UFormField label="CEP" class="sm:col-span-2">
                <UInput v-model="draft.address_zip" placeholder="30110-000" @blur="onZipBlur" />
              </UFormField>
            </div>
          </div>

          <div class="space-y-4">
            <h2 class="font-display text-lg font-bold text-highlighted">
              Contato
            </h2>
            <div class="grid gap-4 sm:grid-cols-3">
              <UFormField label="Nome">
                <UInput v-model="draft.contact_name" placeholder="Ana Souza" />
              </UFormField>
              <UFormField label="E-mail">
                <UInput v-model="draft.contact_email" type="email" placeholder="ana@exemplo.com" />
              </UFormField>
              <UFormField label="Telefone">
                <UInput v-model="draft.contact_phone" placeholder="(31) 3333-0000" />
              </UFormField>
            </div>
          </div>
        </section>

        <!-- Etapa 2 — identidade visual -->
        <section v-show="step === 2" class="space-y-4">
          <h2 class="font-display text-lg font-bold text-highlighted">
            Identidade visual do portal
          </h2>
          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="Nome de exibição" required>
              <UInput v-model="draft.display_name" placeholder="Portal Exemplo" />
            </UFormField>
            <UFormField label="E-mail de suporte">
              <UInput v-model="draft.support_email" type="email" placeholder="suporte@exemplo.com" />
            </UFormField>
            <UFormField label="Cor primária">
              <UInput v-model="draft.primary_color" type="color" />
            </UFormField>
            <UFormField label="Cor de destaque">
              <UInput v-model="draft.accent_color" type="color" />
            </UFormField>
            <UFormField
              label="URL do logo"
              class="sm:col-span-2"
              help="Endereço https:// de uma imagem já hospedada — o console ainda não recebe upload."
            >
              <UInput v-model="draft.logo_url" placeholder="https://..." />
            </UFormField>
          </div>
        </section>

        <!-- Etapa 3 — pessoas -->
        <section v-show="step === 3" class="space-y-4">
          <div class="flex items-center justify-between">
            <h2 class="font-display text-lg font-bold text-highlighted">
              Usuários
            </h2>
            <UButton type="button" variant="soft" color="primary" icon="i-lucide-plus" size="sm" @click="addUser">
              Adicionar usuário
            </UButton>
          </div>

          <UAlert color="info" variant="soft" icon="i-lucide-info" :title="CADASTRO_UNICO_HINT" />

          <UCard v-for="(u, i) in draft.users" :key="i" :ui="{ body: 'space-y-4' }">
            <div class="flex items-center justify-between">
              <p class="text-sm font-semibold text-highlighted">
                Usuário {{ i + 1 }}
              </p>
              <UButton
                v-if="draft.users.length > 1"
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
              <UFormField label="Telefone">
                <UInput v-model="u.phone" placeholder="(31) 3333-0000" />
              </UFormField>
              <UFormField label="Ramal">
                <UInput v-model="u.extension" placeholder="204" />
              </UFormField>
              <UFormField label="Senha" required class="sm:col-span-2">
                <UInput v-model="u.password" type="password" />
              </UFormField>
              <UFormField class="sm:col-span-2">
                <UCheckbox
                  v-model="u.email_intake_enabled"
                  label="Libera abertura de chamado por e-mail"
                />
              </UFormField>
            </div>
          </UCard>
        </section>

        <div class="flex items-center gap-3">
          <UButton
            v-if="step > 1"
            type="button"
            variant="ghost"
            color="neutral"
            icon="i-lucide-arrow-left"
            :disabled="submitting"
            @click="back"
          >
            Voltar
          </UButton>
          <UButton
            v-if="step < 3"
            type="button"
            color="primary"
            size="lg"
            icon="i-lucide-arrow-right"
            trailing
            @click="next"
          >
            Avançar
          </UButton>
          <UButton
            v-else
            type="submit"
            color="primary"
            size="lg"
            :loading="submitting"
            icon="i-lucide-rocket"
          >
            Criar cliente
          </UButton>
          <UButton to="/" variant="ghost" color="neutral" :disabled="submitting">
            Cancelar
          </UButton>
        </div>
      </form>
    </template>
  </div>
</template>
