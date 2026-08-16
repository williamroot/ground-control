<script setup lang="ts">
// Edição do cadastro do cliente (T-R1.5, aceite A1.1/A1.2).
//
// Antes desta onda não existia: errou o CNPJ na criação, ficou errado para
// sempre. Subdomínio e ID do Znuny aparecem DESABILITADOS com a explicação do
// porquê — esconder os dois faria o operador procurar onde os edita.
definePageMeta({ middleware: 'admin-auth' })

interface TenantDetail {
  id: string
  legal_name: string
  trade_name: string
  document: string
  subdomain: string
  znuny_customer_id: string
  address_street: string | null
  address_number: string | null
  address_complement: string | null
  address_district: string | null
  address_city: string | null
  address_state: string | null
  address_zip: string | null
  contact_name: string | null
  contact_email: string | null
  contact_phone: string | null
}

const route = useRoute()
const id = route.params.id as string
const headers = useRequestHeaders(['cookie'])

const { data: tenant, error: loadError } = await useAsyncData(`admin-tenant-edit-${id}`, () =>
  $fetch<TenantDetail | null>(`/api/admin/tenants/${id}`, { headers }).catch(() => null))

const form = reactive({
  legal_name: '',
  trade_name: '',
  document: '',
  address_street: '',
  address_number: '',
  address_complement: '',
  address_district: '',
  address_city: '',
  address_state: '',
  address_zip: '',
  contact_name: '',
  contact_email: '',
  contact_phone: '',
})

watchEffect(() => {
  const t = tenant.value
  if (!t) return
  form.legal_name = t.legal_name ?? ''
  form.trade_name = t.trade_name ?? ''
  form.document = t.document ?? ''
  form.address_street = t.address_street ?? ''
  form.address_number = t.address_number ?? ''
  form.address_complement = t.address_complement ?? ''
  form.address_district = t.address_district ?? ''
  form.address_city = t.address_city ?? ''
  form.address_state = t.address_state ?? ''
  form.address_zip = t.address_zip ?? ''
  form.contact_name = t.contact_name ?? ''
  form.contact_email = t.contact_email ?? ''
  form.contact_phone = t.contact_phone ?? ''
})

const saving = ref(false)
const errorMsg = ref('')
const savedMsg = ref('')

function onZipBlur() {
  form.address_zip = normalizeZip(form.address_zip)
}
function onStateBlur() {
  form.address_state = normalizeState(form.address_state)
}

function validate(): string | null {
  if (!form.legal_name.trim()) return 'Razão social é obrigatória.'
  if (!form.trade_name.trim()) return 'Nome fantasia é obrigatório.'
  if (!form.document.trim()) return 'CNPJ/documento é obrigatório.'
  const zip = normalizeZip(form.address_zip)
  if (form.address_zip.trim() && zip.length !== 8) return 'CEP deve ter 8 dígitos.'
  const email = form.contact_email.trim()
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return 'E-mail de contato inválido.'
  return null
}

async function save() {
  errorMsg.value = ''
  savedMsg.value = ''
  const v = validate()
  if (v) { errorMsg.value = v; return }

  saving.value = true
  try {
    // Campo vazio vai como `null` (limpa), não como ausente: nesta tela o
    // operador está declarando o cadastro inteiro, e apagar precisa apagar.
    const clean = (s: string) => (s.trim() ? s.trim() : null)
    await $fetch(`/api/admin/tenants/${id}`, {
      method: 'PUT',
      body: {
        legal_name: form.legal_name.trim(),
        trade_name: form.trade_name.trim(),
        document: form.document.trim(),
        address_street: clean(form.address_street),
        address_number: clean(form.address_number),
        address_complement: clean(form.address_complement),
        address_district: clean(form.address_district),
        address_city: clean(form.address_city),
        address_state: clean(normalizeState(form.address_state)),
        address_zip: clean(normalizeZip(form.address_zip)),
        contact_name: clean(form.contact_name),
        contact_email: clean(form.contact_email),
        contact_phone: clean(form.contact_phone),
      },
    })
    savedMsg.value = 'Cadastro atualizado.'
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: string } }
    if (err.statusCode === 422) {
      errorMsg.value = err.data?.detail || 'Dados recusados. Confira os campos.'
    }
    else if (err.statusCode === 503) {
      errorMsg.value = 'Znuny indisponível — nada foi alterado. Tente novamente.'
    }
    else if (err.statusCode === 404) {
      errorMsg.value = 'Cliente não encontrado.'
    }
    else {
      errorMsg.value = err.data?.detail || 'Falha ao salvar. Tente novamente.'
    }
  }
  finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-3xl px-5 py-10">
    <ULink :to="`/clientes/${id}`" class="inline-flex items-center gap-1 text-sm text-muted hover:text-default">
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" />
      Voltar para o cliente
    </ULink>

    <UCard v-if="!tenant" class="mt-6 text-center">
      <div class="flex flex-col items-center gap-3 py-12">
        <UIcon name="i-lucide-search-x" class="h-10 w-10 text-muted" />
        <p class="font-display text-lg font-semibold text-highlighted">
          {{ loadError ? 'Falha ao carregar o cliente' : 'Cliente não encontrado' }}
        </p>
        <UButton to="/" variant="soft" color="primary">
          Voltar à lista
        </UButton>
      </div>
    </UCard>

    <template v-else>
      <header class="mt-3 mb-8">
        <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
          Editar cadastro
        </h1>
        <p class="mt-1 text-sm text-muted">
          {{ tenant.trade_name }} · {{ tenant.subdomain }}
        </p>
      </header>

      <form class="space-y-8" @submit.prevent="save">
        <UAlert
          v-if="errorMsg"
          color="error"
          variant="soft"
          icon="i-lucide-alert-triangle"
          :title="errorMsg"
        />
        <UAlert
          v-if="savedMsg"
          color="success"
          variant="soft"
          icon="i-lucide-check"
          :title="savedMsg"
        />

        <section class="space-y-4">
          <h2 class="font-display text-lg font-bold text-highlighted">
            Dados cadastrais
          </h2>
          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="Razão social" required>
              <UInput v-model="form.legal_name" />
            </UFormField>
            <UFormField label="Nome fantasia" required>
              <UInput v-model="form.trade_name" />
            </UFormField>
            <UFormField label="CNPJ / Documento" required>
              <UInput v-model="form.document" />
            </UFormField>
            <UFormField
              label="Subdomínio"
              help="Não pode ser alterado: é a chave do portal white-label e das sessões do cliente."
            >
              <UInput :model-value="tenant.subdomain" disabled />
            </UFormField>
            <UFormField
              label="ID do cliente no Znuny"
              help="Não pode ser alterado: é o vínculo com todos os chamados deste cliente."
            >
              <UInput :model-value="tenant.znuny_customer_id" disabled />
            </UFormField>
          </div>
        </section>

        <section class="space-y-4">
          <h2 class="font-display text-lg font-bold text-highlighted">
            Endereço
          </h2>
          <div class="grid gap-4 sm:grid-cols-6">
            <UFormField label="Logradouro" class="sm:col-span-4">
              <UInput v-model="form.address_street" />
            </UFormField>
            <UFormField label="Número" class="sm:col-span-2">
              <UInput v-model="form.address_number" />
            </UFormField>
            <UFormField label="Complemento" class="sm:col-span-3">
              <UInput v-model="form.address_complement" />
            </UFormField>
            <UFormField label="Bairro" class="sm:col-span-3">
              <UInput v-model="form.address_district" />
            </UFormField>
            <UFormField label="Cidade" class="sm:col-span-3">
              <UInput v-model="form.address_city" />
            </UFormField>
            <UFormField label="UF" class="sm:col-span-1">
              <UInput v-model="form.address_state" @blur="onStateBlur" />
            </UFormField>
            <UFormField label="CEP" class="sm:col-span-2">
              <UInput v-model="form.address_zip" @blur="onZipBlur" />
            </UFormField>
          </div>
        </section>

        <section class="space-y-4">
          <h2 class="font-display text-lg font-bold text-highlighted">
            Contato
          </h2>
          <div class="grid gap-4 sm:grid-cols-3">
            <UFormField label="Nome">
              <UInput v-model="form.contact_name" />
            </UFormField>
            <UFormField label="E-mail">
              <UInput v-model="form.contact_email" type="email" />
            </UFormField>
            <UFormField label="Telefone">
              <UInput v-model="form.contact_phone" />
            </UFormField>
          </div>
        </section>

        <div class="flex items-center gap-3">
          <UButton type="submit" color="primary" size="lg" :loading="saving" icon="i-lucide-save">
            Salvar
          </UButton>
          <UButton :to="`/clientes/${id}`" variant="ghost" color="neutral" :disabled="saving">
            Cancelar
          </UButton>
        </div>
      </form>
    </template>
  </div>
</template>
