<script setup lang="ts">
import type { Branding } from '#shared/branding'
import { DEFAULT_BRANDING } from '#shared/branding'

// Home do help-desk (Spec #1H). A feature de tickets é #1E (deferida); aqui
// fica um placeholder branded "em breve". A guarda (middleware auth) garante sessão.
definePageMeta({ middleware: 'auth' })
const branding = useState<Branding>('branding', () => DEFAULT_BRANDING)
const tenantName = computed(() => branding.value?.display_name ?? 'Portal')
const { data: me } = await useMe()
</script>

<template>
  <div class="mx-auto max-w-3xl px-5 py-10">
    <header class="mb-8">
      <p class="text-sm text-muted">{{ tenantName }}</p>
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Tickets
      </h1>
      <p class="mt-1 text-sm text-muted">
        Acompanhamento e abertura de chamados de suporte.
      </p>
    </header>

    <UCard class="overflow-hidden">
      <div class="flex flex-col items-center gap-5 py-12 text-center">
        <span
          class="inline-flex h-16 w-16 items-center justify-center rounded-2xl text-white shadow-sm"
          :style="{ background: 'linear-gradient(135deg, var(--brand-primary), var(--brand-accent))' }"
        >
          <UIcon name="i-lucide-ticket" class="h-8 w-8" />
        </span>
        <div>
          <div class="mb-2 flex items-center justify-center gap-2">
            <h2 class="font-display text-xl font-bold tracking-tight text-highlighted">
              Em breve
            </h2>
            <UBadge color="primary" variant="subtle" size="sm">próxima entrega</UBadge>
          </div>
          <p class="mx-auto max-w-md text-sm leading-relaxed text-muted">
            Esta é a área da <strong>operação</strong>: aqui o time de help-desk vai
            acompanhar os chamados, abrir novos tickets e ver o andamento dos
            atendimentos — tudo com a marca da {{ tenantName }}.
          </p>
        </div>
        <div
          v-if="me?.role === 'helpdesk'"
          class="rounded-lg border border-default bg-elevated px-4 py-3 text-xs text-muted"
        >
          Você está conectado como <strong>Help Desk</strong>. O acesso a contratos e
          valores é restrito ao perfil <strong>Administrador</strong> do cliente.
        </div>
      </div>
    </UCard>
  </div>
</template>
