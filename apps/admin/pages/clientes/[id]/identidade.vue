<script setup lang="ts">
// Editor de identidade visual do tenant (Spec #3, V4) — preview ao vivo
// lado a lado. Lógica de validação/payload em composables/useBranding.ts
// (testável sem Nuxt). O preview mostra as cores REAIS que o portal do
// cliente vai renderizar (não os tokens do console) — por isso usa valores
// crus aqui, de propósito: é uma simulação do resultado final, não a UI do
// console em si.
import {
  buildBrandingPayload,
  emptyBrandingDraft,
  parseValidationErrors,
  THEME_OPTIONS,
  validateBrandingDraft,
  type BrandingDraft,
} from '../../../composables/useBranding'

definePageMeta({ middleware: 'admin-auth' })

interface TenantSummary {
  id: string
  trade_name: string
}

interface BrandingResponse {
  display_name: string
  primary_color: string
  accent_color: string
  logo_url: string | null
  default_theme: 'light' | 'dark' | 'system'
}

const route = useRoute()
const tenantId = route.params.id as string
const headers = useRequestHeaders(['cookie'])
const toast = useToast()

const { data: tenant } = await useAsyncData(`identidade-tenant-${tenantId}`, () =>
  $fetch<TenantSummary | null>(`/api/admin/tenants/${tenantId}`, { headers }).catch(() => null))

const { data: branding, pending, refresh } = await useAsyncData(`identidade-branding-${tenantId}`, () =>
  $fetch<BrandingResponse | null>(`/api/admin/tenants/${tenantId}/branding`, { headers }).catch(() => null))

const loadFailed = computed(() => !pending.value && branding.value === null)

const draft = reactive<BrandingDraft>(emptyBrandingDraft())

watch(branding, (b) => {
  if (!b) return
  draft.display_name = b.display_name
  draft.primary_color = b.primary_color
  draft.accent_color = b.accent_color
  draft.logo_url = b.logo_url ?? ''
  draft.default_theme = b.default_theme
}, { immediate: true })

const themeOptions = THEME_OPTIONS.map(t => ({
  label: t === 'light' ? 'Claro' : t === 'dark' ? 'Escuro' : 'Sistema',
  value: t,
}))

const clientErrors = computed(() => validateBrandingDraft(draft))
const serverErrors = ref<Record<string, string>>({})
const fieldError = (field: string) => serverErrors.value[field] || clientErrors.value[field] || ''

const saving = ref(false)
const saveOk = ref(false)

async function save() {
  saveOk.value = false
  serverErrors.value = {}
  if (Object.keys(clientErrors.value).length > 0) return

  saving.value = true
  try {
    await $fetch(`/api/admin/tenants/${tenantId}/branding`, {
      method: 'PUT',
      body: buildBrandingPayload(draft),
    })
    saveOk.value = true
    toast.add({ title: 'Identidade visual salva', color: 'success' })
    await refresh()
  }
  catch (e) {
    const err = e as { statusCode?: number, data?: { detail?: unknown } }
    if (err.statusCode === 422) {
      serverErrors.value = parseValidationErrors(err.data?.detail)
      toast.add({ title: 'Não foi possível salvar', description: 'Revise os campos destacados.', color: 'error' })
    }
    else {
      const msg = typeof err.data?.detail === 'string' ? err.data.detail : 'Falha ao salvar a identidade visual.'
      toast.add({ title: 'Não foi possível salvar', description: msg, color: 'error' })
    }
  }
  finally {
    saving.value = false
  }
}

// Preview: default_theme=system segue o SO do navegador — só disponível após
// montar (SSR-safe).
const systemPrefersDark = ref(false)
onMounted(() => {
  systemPrefersDark.value = window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
})
const previewIsDark = computed(() => {
  if (draft.default_theme === 'dark') return true
  if (draft.default_theme === 'light') return false
  return systemPrefersDark.value
})
</script>

<template>
  <div class="mx-auto max-w-6xl px-5 py-10">
    <ULink :to="`/clientes/${tenantId}`" class="inline-flex items-center gap-1 text-sm text-muted hover:text-default">
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" />
      Voltar para o cliente
    </ULink>

    <header class="mt-3 mb-6">
      <h1 class="font-display text-2xl font-extrabold tracking-tight text-highlighted">
        Identidade visual
      </h1>
      <p class="mt-1 text-sm text-muted">
        Cliente: <span class="font-medium text-default">{{ tenant?.trade_name || tenantId }}</span>
      </p>
    </header>

    <div v-if="pending" class="space-y-3">
      <div v-for="n in 3" :key="n" class="h-16 animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <UCard v-else-if="loadFailed" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
        <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar</p>
        <p class="max-w-sm text-sm text-muted">
          Falha ao buscar a identidade visual deste cliente. Tente novamente.
        </p>
        <UButton variant="soft" color="primary" icon="i-lucide-refresh-cw" @click="refresh">
          Tentar novamente
        </UButton>
      </div>
    </UCard>

    <div v-else class="grid gap-6 lg:grid-cols-2">
      <!-- Formulário -->
      <UCard :ui="{ body: 'space-y-4' }">
        <UAlert
          v-if="serverErrors['']"
          color="error"
          variant="soft"
          icon="i-lucide-alert-triangle"
          :title="serverErrors['']"
        />
        <UAlert
          v-if="saveOk"
          color="success"
          variant="soft"
          icon="i-lucide-check"
          title="Identidade visual salva com sucesso."
        />

        <UFormField label="Nome de exibição" required :error="fieldError('display_name')">
          <UInput v-model="draft.display_name" placeholder="Nome que aparece no portal" class="w-full" />
        </UFormField>

        <UFormField label="Cor primária" required :error="fieldError('primary_color')">
          <div class="flex items-center gap-2">
            <input
              v-model="draft.primary_color"
              type="color"
              aria-label="Selecionar cor primária"
              class="h-9 w-11 shrink-0 cursor-pointer rounded border border-default bg-transparent"
            >
            <UInput v-model="draft.primary_color" placeholder="#4f46e5" class="flex-1" />
          </div>
        </UFormField>

        <UFormField label="Cor de destaque" required :error="fieldError('accent_color')">
          <div class="flex items-center gap-2">
            <input
              v-model="draft.accent_color"
              type="color"
              aria-label="Selecionar cor de destaque"
              class="h-9 w-11 shrink-0 cursor-pointer rounded border border-default bg-transparent"
            >
            <UInput v-model="draft.accent_color" placeholder="#4338ca" class="flex-1" />
          </div>
        </UFormField>

        <UFormField label="URL do logo" help="Opcional — precisa começar com https://" :error="fieldError('logo_url')">
          <UInput v-model="draft.logo_url" placeholder="https://exemplo.com/logo.svg" class="w-full" />
        </UFormField>

        <UFormField label="Tema padrão" required :error="fieldError('default_theme')">
          <USelect v-model="draft.default_theme" :items="themeOptions" class="w-full" />
        </UFormField>

        <div class="flex items-center gap-3 pt-2">
          <UButton
            color="primary"
            icon="i-lucide-check"
            :loading="saving"
            :disabled="Object.keys(clientErrors).length > 0"
            @click="save"
          >
            Salvar
          </UButton>
        </div>
      </UCard>

      <!-- Preview ao vivo -->
      <div>
        <p class="mb-3 text-xs uppercase tracking-wide text-dimmed">Preview ao vivo</p>
        <div
          class="overflow-hidden rounded-xl border border-default shadow-sm transition-colors"
          :style="{
            background: previewIsDark ? '#0f1117' : '#f6f7fb',
            color: previewIsDark ? '#f1f2f5' : '#111318',
          }"
        >
          <div
            class="flex items-center justify-between px-5 py-4"
            :style="{ background: draft.primary_color, color: '#ffffff' }"
          >
            <div class="flex items-center gap-2 font-display font-bold">
              <img v-if="draft.logo_url" :src="draft.logo_url" alt="" class="h-6 w-6 rounded object-contain">
              <span>{{ draft.display_name || 'Nome do cliente' }}</span>
            </div>
            <span class="rounded-full bg-white/20 px-2 py-0.5 text-xs">Portal</span>
          </div>

          <div class="space-y-4 p-5">
            <div
              class="rounded-lg border p-4"
              :style="{
                borderColor: previewIsDark ? '#262a35' : '#e3e5ea',
                background: previewIsDark ? '#171a22' : '#ffffff',
              }"
            >
              <p class="mb-1 text-sm font-semibold">Chamado #1234</p>
              <p class="text-xs opacity-70">
                Exemplo de card do portal — mostra como o texto e as bordas ficam com o tema
                {{ draft.default_theme === 'light' ? 'claro' : draft.default_theme === 'dark' ? 'escuro' : 'do sistema' }}.
              </p>
            </div>

            <div class="flex flex-wrap gap-3">
              <button
                type="button"
                class="rounded-lg px-4 py-2 text-sm font-medium text-white"
                :style="{ background: draft.primary_color }"
              >
                Ação primária
              </button>
              <button
                type="button"
                class="rounded-lg px-4 py-2 text-sm font-medium text-white"
                :style="{ background: draft.accent_color }"
              >
                Ação de destaque
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
