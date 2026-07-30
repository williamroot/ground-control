<script setup lang="ts">
import type { Branding } from '#shared/branding'
import { DEFAULT_BRANDING } from '#shared/branding'

// Spec #3 · V1 — Artigo completo. O sidecar incrementa `views` nesta leitura
// e devolve 404 se o slug não existir ou não for público/publicado — o proxy
// vira `null`, tratado aqui como "Artigo não encontrado" (o motivo exato
// — 404 real ou indisponibilidade — não muda a ação do cliente: voltar e
// tentar de novo pela lista). Corpo é markdown; renderizado SEM `v-html` por
// components/kb/MarkdownBody.vue (ver markdown.ts para a análise de segurança).
definePageMeta({ middleware: 'auth' })

interface ArticleDetail {
  id: string
  slug: string
  title: string
  summary: string | null
  category: string
  tags: string[]
  views: number
  updated_at: string
  body_markdown: string
}

const route = useRoute()
const slug = computed(() => String(route.params.slug))
const headers = useSidecarHeaders()
const branding = useState<Branding>('branding', () => DEFAULT_BRANDING)
const tenantName = computed(() => branding.value?.display_name ?? 'Portal')

const { data: article, pending } = await useAsyncData(`kb-article-${slug.value}`, () =>
  $fetch<ArticleDetail | null>(`/api/portal/kb/articles/${encodeURIComponent(slug.value)}`, { headers })
    .catch(() => null))

const notFound = computed(() => !pending.value && !article.value)

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('pt-BR')
}
</script>

<template>
  <div class="mx-auto max-w-3xl px-5 py-8">
    <NuxtLink
      to="/base-conhecimento"
      class="mb-6 inline-flex items-center gap-1.5 text-sm text-muted transition hover:text-highlighted"
    >
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" /> Voltar para a base de conhecimento
    </NuxtLink>

    <!-- Loading -->
    <div v-if="pending" class="space-y-3">
      <div class="h-8 w-2/3 animate-pulse rounded-lg bg-elevated" />
      <div class="h-4 w-1/3 animate-pulse rounded-lg bg-elevated" />
      <div class="h-[240px] animate-pulse rounded-xl border border-default bg-elevated" />
    </div>

    <!-- Não encontrado -->
    <UCard v-else-if="notFound" class="text-center">
      <div class="flex flex-col items-center gap-4 py-12">
        <span class="inline-flex h-12 w-12 items-center justify-center rounded-full bg-elevated text-dimmed">
          <UIcon name="i-lucide-search-x" class="h-6 w-6" />
        </span>
        <div>
          <p class="font-display text-lg font-semibold text-highlighted">Artigo não encontrado</p>
          <p class="mx-auto mt-1 max-w-sm text-sm text-muted">
            Este artigo não existe ou não está mais disponível.
          </p>
        </div>
        <UButton to="/base-conhecimento" color="neutral" variant="subtle" icon="i-lucide-arrow-left" label="Ver todos os artigos" />
      </div>
    </UCard>

    <template v-else-if="article">
      <p class="text-sm text-muted">{{ tenantName }}</p>
      <header class="mb-6">
        <div class="mb-2 flex flex-wrap items-center gap-2">
          <UBadge color="neutral" variant="subtle" size="sm">{{ article.category }}</UBadge>
          <span class="inline-flex items-center gap-1 text-xs text-dimmed">
            <UIcon name="i-lucide-eye" class="h-3.5 w-3.5" />{{ article.views }} visualizações
          </span>
        </div>
        <h1 class="font-display text-2xl font-extrabold tracking-tight text-highlighted sm:text-3xl">
          {{ article.title }}
        </h1>
        <p v-if="article.summary" class="mt-2 text-sm text-muted">{{ article.summary }}</p>
        <p class="mt-2 text-xs text-dimmed">Atualizado em {{ fmtDate(article.updated_at) }}</p>
      </header>

      <UCard class="mb-6">
        <MarkdownBody :source="article.body_markdown" />
      </UCard>

      <div v-if="article.tags.length" class="flex flex-wrap gap-2">
        <UBadge v-for="t in article.tags" :key="t" color="neutral" variant="outline" size="sm">{{ t }}</UBadge>
      </div>
    </template>
  </div>
</template>
