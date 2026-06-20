<script setup lang="ts">
interface Plan {
  slug: string
  name: string
  description: string | null
  audience: string
  billing_mode: string
  price_cents: number
  cycle: string | null
}

const { data: plans } = await useFetch<Plan[]>('/api/checkout/plans', { default: () => [] })

const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
function price(p: Plan): string {
  const v = brl.format(p.price_cents / 100)
  return p.billing_mode === 'subscription' ? `${v}/mês` : v
}
</script>

<template>
  <div class="mx-auto max-w-4xl px-5 py-10">
    <header class="mb-8">
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Escolha seu plano
      </h1>
      <p class="mt-1 text-sm text-muted">
        Contrate em minutos. Pague por PIX, boleto ou cartão — o acesso é liberado assim que o pagamento é confirmado.
      </p>
    </header>

    <UCard v-if="!plans || plans.length === 0" class="text-center">
      <div class="py-12 text-sm text-muted">
        Nenhum plano disponível no momento.
      </div>
    </UCard>

    <div v-else class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
      <UCard v-for="p in plans" :key="p.slug" class="flex h-full flex-col" :ui="{ body: 'flex-1 space-y-3' }">
        <div>
          <p class="font-display text-lg font-bold tracking-tight text-highlighted">{{ p.name }}</p>
          <UBadge color="neutral" variant="subtle" size="sm" class="mt-1">
            {{ p.billing_mode === 'subscription' ? 'Assinatura' : 'Pagamento único' }}
          </UBadge>
        </div>
        <p v-if="p.description" class="text-sm text-muted">{{ p.description }}</p>
        <p class="font-display text-2xl font-extrabold tracking-tight text-highlighted">
          {{ price(p) }}
        </p>
        <template #footer>
          <UButton :to="`/contratar/${p.slug}`" color="primary" block label="Contratar" />
        </template>
      </UCard>
    </div>
  </div>
</template>
