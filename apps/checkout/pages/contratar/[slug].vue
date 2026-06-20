<script setup lang="ts">
interface Plan {
  slug: string
  name: string
  billing_mode: string
  price_cents: number
}
interface StartResult {
  session_id: string
  guest_token: string
  status: string
  billing_type: string
  value_cents: number
  invoice_url: string | null
  pix?: { qrcode_base64: string | null, copy_paste: string | null, expiration: string | null }
  boleto?: { url: string | null, linha_digitavel: string | null }
}
interface StatusResult { status: string, subdomain?: string, portal_url?: string | null }

const route = useRoute()
const slug = computed(() => String(route.params.slug))

const { data: plans } = await useFetch<Plan[]>('/api/checkout/plans', { default: () => [] })
const plan = computed(() => (plans.value ?? []).find(p => p.slug === slug.value) ?? null)

const form = reactive({
  legal_name: '',
  trade_name: '',
  document: '',
  subdomain: '',
  znuny_customer_id: '',
  admin_email: '',
  admin_first: '',
  admin_last: '',
  admin_password: '',
  billing_type: 'PIX',
  // cartão (só quando CREDIT_CARD)
  card_holder: '',
  card_number: '',
  card_month: '',
  card_year: '',
  card_ccv: '',
})
const billingOptions = [
  { label: 'PIX', value: 'PIX' },
  { label: 'Boleto', value: 'BOLETO' },
  { label: 'Cartão de crédito', value: 'CREDIT_CARD' },
]

const submitting = ref(false)
const error = ref('')
const result = ref<StartResult | null>(null)
const finalStatus = ref<StatusResult | null>(null)
let pollHandle: ReturnType<typeof setInterval> | null = null

async function submit() {
  error.value = ''
  if (!form.document || !form.subdomain || !form.znuny_customer_id || !form.admin_email || !form.admin_password) {
    error.value = 'Preencha os campos obrigatórios.'
    return
  }
  submitting.value = true
  try {
    const body: Record<string, unknown> = {
      plan_slug: slug.value,
      billing_type: form.billing_type,
      company: { legal_name: form.legal_name || form.trade_name, trade_name: form.trade_name || form.legal_name, document: form.document },
      subdomain: form.subdomain,
      znuny_customer_id: form.znuny_customer_id,
      admin: { email: form.admin_email, first_name: form.admin_first, last_name: form.admin_last, password: form.admin_password },
    }
    if (form.billing_type === 'CREDIT_CARD') {
      body.credit_card = {
        holderName: form.card_holder,
        number: form.card_number.replace(/\s/g, ''),
        expiryMonth: form.card_month,
        expiryYear: form.card_year,
        ccv: form.card_ccv,
        holderInfo: { name: form.card_holder, email: form.admin_email, cpfCnpj: form.document },
      }
    }
    result.value = await $fetch<StartResult>('/api/checkout/sessions', { method: 'POST', body })
    startPolling()
  }
  catch (e: unknown) {
    const err = e as { data?: { detail?: unknown } }
    const d = err.data?.detail
    error.value = Array.isArray(d) ? d.join('; ') : (typeof d === 'string' ? d : 'Não foi possível iniciar a contratação.')
  }
  finally {
    submitting.value = false
  }
}

function startPolling() {
  if (!result.value) return
  const id = result.value.session_id
  const token = result.value.guest_token
  pollHandle = setInterval(async () => {
    try {
      const st = await $fetch<StatusResult>(`/api/checkout/sessions/${id}`, { query: { token } })
      if (st.status === 'provisioned') {
        finalStatus.value = st
        if (pollHandle) clearInterval(pollHandle)
      }
    }
    catch { /* segue tentando */ }
  }, 4000)
}

onBeforeUnmount(() => { if (pollHandle) clearInterval(pollHandle) })

const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
</script>

<template>
  <div class="mx-auto max-w-2xl px-5 py-10">
    <ULink to="/" class="mb-6 inline-flex items-center gap-1 text-sm text-muted hover:text-default">
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" /> Voltar aos planos
    </ULink>

    <!-- Sucesso: provisionado -->
    <UCard v-if="finalStatus" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-party-popper" class="h-12 w-12 text-success" />
        <h1 class="font-display text-2xl font-extrabold text-highlighted">Tudo pronto!</h1>
        <p class="text-sm text-muted">Pagamento confirmado e ambiente provisionado.</p>
        <UButton v-if="finalStatus.portal_url" :to="finalStatus.portal_url" external color="primary" size="lg" label="Acessar o portal" />
        <p class="text-xs text-dimmed">Use o e-mail e a senha que você definiu para entrar.</p>
      </div>
    </UCard>

    <!-- Pagamento -->
    <div v-else-if="result">
      <h1 class="font-display text-2xl font-extrabold tracking-tight text-highlighted">Pagamento</h1>
      <p class="mt-1 text-sm text-muted">
        {{ brl.format(result.value_cents / 100) }} · aguardando confirmação… o acesso é liberado automaticamente.
      </p>

      <UCard class="mt-6">
        <div v-if="result.pix" class="flex flex-col items-center gap-3">
          <img v-if="result.pix.qrcode_base64" :src="`data:image/png;base64,${result.pix.qrcode_base64}`" alt="QR PIX" class="h-56 w-56">
          <UFormField label="PIX copia e cola" class="w-full">
            <UTextarea :model-value="result.pix.copy_paste || ''" readonly :rows="3" class="w-full font-mono text-xs" />
          </UFormField>
        </div>
        <div v-else-if="result.boleto" class="space-y-3">
          <UButton v-if="result.boleto.url" :to="result.boleto.url" external color="primary" icon="i-lucide-file-text" label="Abrir boleto (PDF)" />
          <UFormField label="Linha digitável">
            <UInput :model-value="result.boleto.linha_digitavel || ''" readonly class="w-full font-mono text-xs" />
          </UFormField>
        </div>
        <div v-else class="text-sm text-muted">
          Processando o pagamento…
        </div>
        <template #footer>
          <UButton v-if="result.invoice_url" :to="result.invoice_url" external variant="link" color="neutral" label="Abrir página de pagamento do Asaas" />
        </template>
      </UCard>
      <p class="mt-4 flex items-center justify-center gap-2 text-sm text-muted">
        <UIcon name="i-lucide-loader-circle" class="h-4 w-4 animate-spin" /> Aguardando pagamento…
      </p>
    </div>

    <!-- Formulário -->
    <div v-else>
      <h1 class="font-display text-2xl font-extrabold tracking-tight text-highlighted">
        Contratar {{ plan?.name || slug }}
      </h1>
      <UCard class="mt-6">
        <UForm :state="form" class="space-y-5" @submit="submit">
          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="Razão social"><UInput v-model="form.legal_name" class="w-full" /></UFormField>
            <UFormField label="Nome fantasia"><UInput v-model="form.trade_name" class="w-full" /></UFormField>
            <UFormField label="CNPJ" required><UInput v-model="form.document" class="w-full" placeholder="00.000.000/0001-00" /></UFormField>
            <UFormField label="Subdomínio" required help="seu-sub.was.dev.br"><UInput v-model="form.subdomain" class="w-full" /></UFormField>
            <UFormField label="Identificador (Znuny ID)" required><UInput v-model="form.znuny_customer_id" class="w-full" /></UFormField>
          </div>
          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="E-mail do administrador" required><UInput v-model="form.admin_email" type="email" class="w-full" /></UFormField>
            <UFormField label="Senha de acesso" required><UInput v-model="form.admin_password" type="password" class="w-full" /></UFormField>
            <UFormField label="Nome"><UInput v-model="form.admin_first" class="w-full" /></UFormField>
            <UFormField label="Sobrenome"><UInput v-model="form.admin_last" class="w-full" /></UFormField>
          </div>
          <UFormField label="Forma de pagamento">
            <USelect v-model="form.billing_type" :items="billingOptions" class="w-full" />
          </UFormField>
          <div v-if="form.billing_type === 'CREDIT_CARD'" class="grid gap-4 sm:grid-cols-2 rounded-lg border border-default p-4">
            <UFormField label="Nome no cartão" class="sm:col-span-2"><UInput v-model="form.card_holder" class="w-full" /></UFormField>
            <UFormField label="Número" class="sm:col-span-2"><UInput v-model="form.card_number" class="w-full" /></UFormField>
            <UFormField label="Mês (MM)"><UInput v-model="form.card_month" class="w-full" /></UFormField>
            <UFormField label="Ano (AAAA)"><UInput v-model="form.card_year" class="w-full" /></UFormField>
            <UFormField label="CVV"><UInput v-model="form.card_ccv" class="w-full" /></UFormField>
          </div>
          <UAlert v-if="error" color="error" variant="soft" icon="i-lucide-alert-circle" :title="error" />
          <div class="flex justify-end">
            <UButton type="submit" color="primary" size="lg" :loading="submitting" label="Ir para o pagamento" />
          </div>
        </UForm>
      </UCard>
    </div>
  </div>
</template>
