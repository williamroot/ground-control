<script setup lang="ts">
import type { Branding } from '#shared/branding'
import { DEFAULT_BRANDING } from '#shared/branding'

definePageMeta({ layout: 'default' })

// Lê o MESMO state que o layout populou no SSR (sem refetch, sem flash).
const branding = useState<Branding>('branding', () => DEFAULT_BRANDING)
const b = computed(() => branding.value)

const state = reactive({ username: '', password: '' })
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  const res = await $fetch<{ ok: boolean, status?: number }>(
    '/api/auth/login',
    { method: 'POST', body: { username: state.username, password: state.password } },
  ).catch(() => ({ ok: false }))
  loading.value = false
  if (res.ok) await navigateTo('/')
  else error.value = 'Credenciais inválidas ou serviço indisponível.'
}
</script>

<template>
  <div class="relative grid min-h-[calc(100vh-3px)] lg:grid-cols-2">
    <!-- Seletor de tema (claro/escuro/sistema) sempre acessível -->
    <div class="absolute right-4 top-4 z-10">
      <ThemeToggle />
    </div>

    <!-- Painel da marca -->
    <section
      class="relative hidden flex-col justify-between overflow-hidden p-12 text-white lg:flex"
      :style="{ background: 'linear-gradient(150deg, var(--brand-primary), var(--brand-accent))' }"
    >
      <!-- textura discreta -->
      <div
        class="pointer-events-none absolute inset-0 opacity-[0.12]"
        style="background-image: radial-gradient(circle at 1px 1px, #fff 1px, transparent 0); background-size: 22px 22px;"
      />
      <div class="relative flex items-center gap-2.5">
        <span class="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-white/15 font-display text-lg font-bold backdrop-blur">
          {{ (b?.display_name ?? 'P').charAt(0) }}
        </span>
        <span class="text-sm font-medium tracking-wide text-white/80">Portal do cliente</span>
      </div>
      <div class="relative">
        <h1 class="font-display text-5xl font-extrabold leading-[1.05] tracking-tight">
          {{ b?.display_name ?? 'Portal' }}
        </h1>
        <p class="mt-4 max-w-sm text-base leading-relaxed text-white/80">
          Acompanhe seus contratos, saldos e atendimentos em um só lugar.
        </p>
      </div>
      <p v-if="b?.support_email" class="relative text-sm text-white/70">
        Precisa de ajuda? {{ b.support_email }}
      </p>
    </section>

    <!-- Painel do formulário -->
    <section class="flex items-center justify-center bg-default px-6 py-12">
      <div class="w-full max-w-sm">
        <div class="mb-8 lg:hidden">
          <h1 class="font-display text-3xl font-extrabold tracking-tight">
            {{ b?.display_name ?? 'Portal' }}
          </h1>
          <p class="mt-1 text-sm text-muted">Portal do cliente</p>
        </div>

        <h2 class="font-display text-2xl font-bold tracking-tight">Entrar</h2>
        <p class="mt-1 text-sm text-muted">Use suas credenciais de acesso.</p>

        <UForm :state="state" class="mt-8 space-y-5" @submit="submit">
          <UFormField label="E-mail" name="username">
            <UInput
              v-model="state.username"
              type="email"
              placeholder="voce@empresa.com.br"
              autocomplete="email"
              size="lg"
              class="w-full"
              icon="i-lucide-mail"
            />
          </UFormField>
          <UFormField label="Senha" name="password">
            <UInput
              v-model="state.password"
              type="password"
              placeholder="••••••••"
              autocomplete="current-password"
              size="lg"
              class="w-full"
              icon="i-lucide-lock"
            />
          </UFormField>

          <UAlert
            v-if="error"
            color="error"
            variant="soft"
            icon="i-lucide-alert-circle"
            :title="error"
          />

          <UButton
            type="submit"
            color="primary"
            size="lg"
            block
            :loading="loading"
            label="Entrar"
          />
        </UForm>
        <div class="mt-10">
          <WasSignature />
        </div>
      </div>
    </section>
  </div>
</template>
