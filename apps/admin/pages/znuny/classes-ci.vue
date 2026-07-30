<script setup lang="ts">
// Classes de CI do Znuny (Spec #4, Bloco B) — o console é uma CAPA sobre o
// Znuny: nada aqui é persistido localmente, tudo é lido/escrito ao vivo pelo
// GI. Editar a definição de uma classe é arriscado (uma definição quebrada
// derruba o CMDB dos clientes que a usam), então: (1) nunca salvamos sem
// passar pelo `DefinitionCheck` do Znuny — o 422 com a mensagem real é
// exibido em destaque; (2) deixamos explícito que salvar cria uma NOVA
// versão, nunca sobrescreve.
import {
  buildDefinitionPayload,
  ciValidColor,
  ciValidLabel,
  extractDefinitionError,
  isDefinitionDirty,
  isDefinitionSaveable,
  type CiClassDefinition,
  type CiClassRow,
} from '../../composables/useCiDefinition'

definePageMeta({ middleware: 'admin-auth' })

const headers = useRequestHeaders(['cookie'])
const toast = useToast()

interface CiClassListResponse { items: CiClassRow[] }

const { data: listRes, pending, refresh } = await useAsyncData('znuny-ci-classes', () =>
  $fetch<CiClassListResponse | null>('/api/admin/znuny/ci-classes', { headers }).catch(() => null))

const loadFailed = computed(() => !pending.value && listRes.value === null)
const classes = computed(() => listRes.value?.items ?? [])
const isEmpty = computed(() => !pending.value && !loadFailed.value && classes.value.length === 0)

// --- Editor de definição da classe selecionada -------------------------------
const selected = ref<CiClassRow | null>(null)
const defPending = ref(false)
const defLoadFailed = ref(false)
const original = ref('')
const draft = ref('')
const meta = ref<CiClassDefinition | null>(null)

const isDirty = computed(() => isDefinitionDirty(original.value, draft.value))
const canSave = computed(() => isDefinitionSaveable(draft.value) && isDirty.value && !saving.value)

const saving = ref(false)
const saveError = ref('')
const saveOk = ref(false)

async function selectClass(row: CiClassRow) {
  selected.value = row
  saveError.value = ''
  saveOk.value = false
  defPending.value = true
  defLoadFailed.value = false
  const res = await $fetch<CiClassDefinition | null>(
    `/api/admin/znuny/ci-classes/${row.ClassID}/definition`,
    { headers },
  ).catch(() => null)
  defPending.value = false
  if (res === null) {
    defLoadFailed.value = true
    original.value = ''
    draft.value = ''
    meta.value = null
    return
  }
  meta.value = res
  original.value = res.Definition ?? ''
  draft.value = res.Definition ?? ''
}

function revert() {
  draft.value = original.value
  saveError.value = ''
}

async function save() {
  if (!selected.value || !canSave.value) return
  saving.value = true
  saveError.value = ''
  saveOk.value = false
  try {
    const res = await $fetch<CiClassDefinition>(
      `/api/admin/znuny/ci-classes/${selected.value.ClassID}/definition`,
      { method: 'PUT', body: buildDefinitionPayload(draft.value) },
    )
    meta.value = res
    original.value = res.Definition ?? draft.value
    draft.value = original.value
    saveOk.value = true
    toast.add({ title: 'Nova versão gravada no Znuny', color: 'success' })
  }
  catch (e) {
    saveError.value = extractDefinitionError(e)
  }
  finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-6xl px-5 py-10">
    <header class="mb-6">
      <h1 class="font-display text-3xl font-extrabold tracking-tight text-highlighted">
        Classes de CI
      </h1>
      <p class="mt-1 text-sm text-muted">
        Classes de Config Item do CMDB e a definição (estrutura) de cada uma.
      </p>
      <UAlert
        class="mt-4"
        color="warning"
        variant="soft"
        icon="i-lucide-alert-triangle"
        title="Isto edita o Znuny ao vivo"
        description="Nada é guardado pelo console — a leitura e a gravação acontecem direto no Znuny. Uma definição quebrada derruba o CMDB de quem usa essa classe."
      />
    </header>

    <!-- Loading -->
    <div v-if="pending" class="space-y-3">
      <div v-for="n in 4" :key="n" class="h-12 animate-pulse rounded-lg border border-default bg-elevated" />
    </div>

    <!-- Erro -->
    <UCard v-else-if="loadFailed" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-alert-triangle" class="h-10 w-10 text-error" />
        <p class="font-display text-lg font-semibold text-highlighted">Não foi possível carregar as classes</p>
        <UButton variant="soft" color="primary" icon="i-lucide-refresh-cw" @click="refresh()">
          Tentar novamente
        </UButton>
      </div>
    </UCard>

    <!-- Vazio -->
    <UCard v-else-if="isEmpty" class="text-center">
      <div class="flex flex-col items-center gap-3 py-10">
        <UIcon name="i-lucide-boxes" class="h-10 w-10 text-muted" />
        <p class="font-display text-lg font-semibold text-highlighted">Nenhuma classe de CI encontrada</p>
        <p class="max-w-sm text-sm text-muted">O catálogo geral do Znuny não tem classes cadastradas em ITSM::ConfigItem::Class.</p>
      </div>
    </UCard>

    <template v-else>
      <div class="grid gap-6 lg:grid-cols-[20rem_1fr]">
        <!-- Lista de classes -->
        <div class="overflow-hidden rounded-xl border border-default">
          <table class="w-full text-sm">
            <thead class="bg-elevated text-left text-xs uppercase text-muted">
              <tr>
                <th class="px-4 py-2.5">Classe</th>
                <th class="px-4 py-2.5">Validade</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="c in classes"
                :key="String(c.ClassID)"
                class="cursor-pointer border-t border-default hover:bg-elevated/60"
                :class="{ 'bg-elevated/80': selected?.ClassID === c.ClassID }"
                @click="selectClass(c)"
              >
                <td class="px-4 py-3 font-semibold text-highlighted">{{ c.Name }}</td>
                <td class="px-4 py-3">
                  <UBadge :color="ciValidColor(c.ValidID)" variant="soft" size="sm">
                    {{ ciValidLabel(c.ValidID) }}
                  </UBadge>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Editor -->
        <div>
          <UCard v-if="!selected" class="text-center">
            <div class="flex flex-col items-center gap-2 py-10">
              <UIcon name="i-lucide-mouse-pointer-click" class="h-8 w-8 text-muted" />
              <p class="text-sm text-muted">Selecione uma classe à esquerda para ver e editar a definição.</p>
            </div>
          </UCard>

          <UCard v-else>
            <template #header>
              <div class="flex items-center justify-between">
                <div>
                  <h2 class="font-display text-base font-bold text-highlighted">{{ selected.Name }}</h2>
                  <p class="text-xs text-muted">
                    Classe #{{ selected.ClassID }}
                    <template v-if="meta?.DefinitionID"> · definição #{{ meta.DefinitionID }}</template>
                    <template v-if="meta?.CreateTime"> · gravada em {{ meta.CreateTime }}</template>
                  </p>
                </div>
              </div>
            </template>

            <div v-if="defPending" class="h-64 animate-pulse rounded-lg bg-elevated" />

            <div v-else-if="defLoadFailed" class="flex flex-col items-center gap-3 py-10 text-center">
              <UIcon name="i-lucide-alert-triangle" class="h-8 w-8 text-error" />
              <p class="text-sm text-muted">Não foi possível carregar a definição desta classe.</p>
              <UButton variant="soft" color="primary" icon="i-lucide-refresh-cw" @click="selectClass(selected)">
                Tentar novamente
              </UButton>
            </div>

            <div v-else class="space-y-3">
              <UAlert
                color="info"
                variant="soft"
                icon="i-lucide-history"
                title="Salvar cria uma nova versão"
                description="O Znuny versiona a definição — não existe sobrescrever. A versão anterior continua no histórico do Znuny."
              />

              <label class="block text-xs font-medium uppercase tracking-wide text-muted">
                Definição (YAML)
              </label>
              <textarea
                v-model="draft"
                spellcheck="false"
                rows="20"
                class="w-full rounded-lg border border-default bg-default p-3 font-mono text-xs leading-relaxed text-default outline-none focus:border-primary"
                data-testid="ci-definition-textarea"
              />

              <UAlert
                v-if="saveError"
                color="error"
                variant="soft"
                icon="i-lucide-shield-alert"
                title="O Znuny recusou esta definição"
              >
                <template #description>
                  <pre class="mt-1 whitespace-pre-wrap font-mono text-xs">{{ saveError }}</pre>
                </template>
              </UAlert>

              <UAlert
                v-if="saveOk"
                color="success"
                variant="soft"
                icon="i-lucide-check"
                title="Nova versão gravada no Znuny"
              />

              <div class="flex items-center gap-3">
                <UButton :disabled="!canSave" :loading="saving" color="primary" icon="i-lucide-save" @click="save">
                  Salvar nova versão
                </UButton>
                <UButton :disabled="!isDirty || saving" color="neutral" variant="ghost" @click="revert">
                  Descartar alterações
                </UButton>
                <span v-if="isDirty" class="text-xs text-muted">alterações não salvas</span>
              </div>
            </div>
          </UCard>
        </div>
      </div>
    </template>
  </div>
</template>
