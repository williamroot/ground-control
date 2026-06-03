<script setup lang="ts">
// Login de agente Gerti (Spec #1G-a, T1.E). Identidade FIXA Gerti (NÃO
// white-label): o admin é a casa da equipe Gerti/WAS. Posta em
// /api/admin/auth/login; em sucesso vai para /; mostra erro em 401/503.
import { ADMIN_IDENTITY } from '#shared/identity'

const state = reactive({ login: '', password: '' })
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  const res = await $fetch<{ ok: boolean, status?: number }>(
    '/api/admin/auth/login',
    { method: 'POST', body: { login: state.login, password: state.password } },
  ).catch((e): { ok: boolean, status?: number } => ({
    ok: false,
    status: e?.statusCode,
  }))
  loading.value = false
  if (res.ok) { await navigateTo('/'); return }
  error.value = res.status === 503
    ? 'Serviço indisponível. Tente novamente em instantes.'
    : 'Credenciais inválidas.'
}
</script>

<template>
  <div class="relative grid min-h-[calc(100vh-3px)] lg:grid-cols-2">
    <!-- Painel da marca Gerti -->
    <section
      class="relative hidden flex-col justify-between overflow-hidden p-12 text-white lg:flex"
      :style="{ background: 'linear-gradient(150deg, var(--brand-primary), var(--brand-accent))' }"
    >
      <div
        class="pointer-events-none absolute inset-0 opacity-[0.12]"
        style="background-image: radial-gradient(circle at 1px 1px, #fff 1px, transparent 0); background-size: 22px 22px;"
      />
      <div class="relative flex items-center gap-2.5">
        <span class="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-white/15 font-display text-lg font-bold backdrop-blur">
          {{ ADMIN_IDENTITY.short_name.charAt(0) }}
        </span>
        <span class="text-sm font-medium tracking-wide text-white/80">Console de Administração</span>
      </div>
      <div class="relative">
        <h1 class="font-display text-5xl font-extrabold leading-[1.05] tracking-tight">
          {{ ADMIN_IDENTITY.short_name }}
        </h1>
        <p class="mt-4 max-w-sm text-base leading-relaxed text-white/80">
          Gestão de clientes, contratos e onboarding em um só lugar.
        </p>
      </div>
      <p class="relative text-sm text-white/70">
        Acesso restrito à equipe Gerti.
      </p>
    </section>

    <!-- Painel do formulário -->
    <section class="flex items-center justify-center bg-default px-6 py-12">
      <div class="w-full max-w-sm">
        <div class="mb-8 lg:hidden">
          <span class="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-primary font-display text-lg font-bold text-white">
            {{ ADMIN_IDENTITY.short_name.charAt(0) }}
          </span>
          <h1 class="mt-3 font-display text-2xl font-extrabold tracking-tight">
            {{ ADMIN_IDENTITY.display_name }}
          </h1>
        </div>

        <h2 class="font-display text-2xl font-bold tracking-tight">
          Entrar
        </h2>
        <p class="mt-1 text-sm text-muted">
          Use suas credenciais de agente.
        </p>

        <UForm :state="state" class="mt-8 space-y-5" @submit="submit">
          <UFormField label="Login" name="login">
            <UInput
              v-model="state.login"
              type="text"
              placeholder="agente"
              autocomplete="username"
              size="lg"
              class="w-full"
              icon="i-lucide-user"
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
      </div>
    </section>
  </div>
</template>
