<script setup lang="ts">
// #1R-a — página "Agentes" do console: instalar o agente de inventário (gerar
// token + comando 1×, rotacionar/desabilitar) e gerenciar dispositivos
// (listar/aprovar/revogar). O servidor (sidecar) decide o cliente pelo token —
// o operador nunca digita o cliente. Cores semânticas (H8) nos componentes.
import { computed, ref } from 'vue'
import DeviceRow from '../../../components/agent/DeviceRow.vue'
import InstallCommand from '../../../components/agent/InstallCommand.vue'
import type { AgentToken, Device } from '../../../composables/useAgents'

definePageMeta({ middleware: 'admin-auth' })

const route = useRoute()
const tenantId = route.params.id as string
const headers = useRequestHeaders(['cookie'])
const toast = useToast()

const HEARTBEAT_INTERVAL = 3600

const { data: tokens, refresh: refreshTokens, pending: tokensPending } = await useAsyncData(
  `admin-agent-tokens-${tenantId}`,
  () => $fetch<AgentToken[] | null>(`/api/admin/tenants/${tenantId}/agent-tokens`, { headers })
    .catch(() => null),
)

const { data: devices, refresh: refreshDevices, pending: devicesPending } = await useAsyncData(
  `admin-agent-devices-${tenantId}`,
  () => $fetch<Device[] | null>(`/api/admin/tenants/${tenantId}/devices`, { headers })
    .catch(() => null),
)

// Token recém-criado: { token, install_command } — mostrado UMA vez.
interface CreatedToken { id: string, token: string, install_command: string }
const justCreated = ref<CreatedToken | null>(null)
const generating = ref(false)
const label = ref('')
const maxReg = ref<number | null>(null)

// O servidor (base pública) é autoritativo no install_command do backend; extraio
// daí para o InstallCommand reconstruir o comando idêntico.
const createdServer = computed(() => {
  const cmd = justCreated.value?.install_command ?? ''
  const m = cmd.match(/--server=(\S+)/)
  return m ? m[1] : ''
})

async function generate() {
  generating.value = true
  try {
    const res = await $fetch<CreatedToken>(`/api/admin/tenants/${tenantId}/agent-tokens`, {
      method: 'POST',
      body: {
        label: label.value.trim() || 'instalação',
        max_registrations: maxReg.value ?? null,
      },
    })
    justCreated.value = res
    label.value = ''
    maxReg.value = null
    toast.add({ title: 'Token gerado', description: 'Copie o comando agora.', color: 'success' })
    await refreshTokens()
  }
  catch {
    toast.add({ title: 'Falha ao gerar token', color: 'error' })
  }
  finally {
    generating.value = false
  }
}

async function disableToken(id: string) {
  try {
    await $fetch(`/api/admin/tenants/${tenantId}/agent-tokens/${id}`, { method: 'DELETE' })
    toast.add({ title: 'Token desabilitado', color: 'neutral' })
    await refreshTokens()
  }
  catch {
    toast.add({ title: 'Falha ao desabilitar', color: 'error' })
  }
}

async function approve(deviceId: string) {
  try {
    await $fetch(`/api/admin/tenants/${tenantId}/devices/${deviceId}/approve`, { method: 'POST' })
    toast.add({ title: 'Dispositivo aprovado', color: 'success' })
    await refreshDevices()
  }
  catch (e) {
    const err = e as { statusCode?: number }
    const msg = err.statusCode === 503 ? 'Znuny indisponível — tente de novo.' : 'Falha ao aprovar.'
    toast.add({ title: 'Não foi possível aprovar', description: msg, color: 'error' })
  }
}

async function revoke(deviceId: string) {
  try {
    await $fetch(`/api/admin/tenants/${tenantId}/devices/${deviceId}/revoke`, { method: 'POST' })
    toast.add({ title: 'Dispositivo revogado', color: 'neutral' })
    await refreshDevices()
  }
  catch {
    toast.add({ title: 'Falha ao revogar', color: 'error' })
  }
}

const activeTokens = computed(() => (tokens.value ?? []).filter(t => t.enabled))
</script>

<template>
  <div class="mx-auto max-w-5xl px-5 py-10">
    <ULink :to="`/clientes/${tenantId}`" class="inline-flex items-center gap-1 text-sm text-muted hover:text-default">
      <UIcon name="i-lucide-arrow-left" class="h-4 w-4" />
      Voltar para o cliente
    </ULink>

    <header class="mt-3 mb-6">
      <h1 class="font-display text-2xl font-extrabold tracking-tight text-highlighted">
        Agentes de inventário
      </h1>
      <p class="mt-1 text-sm text-muted">
        Instale o agente nas máquinas do cliente: ele registra o equipamento no inventário (CMDB)
        deste cliente automaticamente. O token decide o cliente — você nunca o digita.
      </p>
    </header>

    <!-- Instalar agente -->
    <UCard class="mb-6">
      <template #header>
        <h2 class="font-display text-base font-bold text-highlighted">Instalar agente</h2>
      </template>

      <div class="flex flex-wrap items-end gap-3">
        <UFormField label="Rótulo (ex.: matriz, filial SP)" class="flex-1 min-w-[220px]">
          <UInput v-model="label" placeholder="instalação" class="w-full" />
        </UFormField>
        <UFormField label="Máx. registros (vazio = ilimitado)" class="w-56">
          <UInput v-model.number="maxReg" type="number" min="1" placeholder="ilimitado" class="w-full" />
        </UFormField>
        <UButton icon="i-lucide-key-round" :loading="generating" label="Gerar token" @click="generate" />
      </div>

      <InstallCommand
        v-if="justCreated && createdServer"
        :server="createdServer"
        :token="justCreated.token"
        class="mt-4"
      />
    </UCard>

    <!-- Tokens existentes -->
    <UCard class="mb-6">
      <template #header>
        <h2 class="font-display text-base font-bold text-highlighted">Tokens de instalação</h2>
      </template>
      <div v-if="tokensPending" class="h-12 animate-pulse rounded-lg bg-elevated" />
      <p v-else-if="activeTokens.length === 0" class="text-sm text-muted">
        Nenhum token ativo. Gere um acima para instalar o agente.
      </p>
      <ul v-else class="divide-y divide-default">
        <li v-for="t in activeTokens" :key="t.id" class="flex items-center justify-between py-2.5">
          <div>
            <div class="font-medium text-highlighted">{{ t.label }}</div>
            <div class="text-xs text-muted">
              {{ t.registration_count }}<template v-if="t.max_registrations != null"> / {{ t.max_registrations }}</template>
              registros
            </div>
          </div>
          <UButton
            size="xs"
            color="neutral"
            variant="soft"
            icon="i-lucide-ban"
            label="Desabilitar"
            @click="disableToken(t.id)"
          />
        </li>
      </ul>
    </UCard>

    <!-- Dispositivos -->
    <UCard>
      <template #header>
        <h2 class="font-display text-base font-bold text-highlighted">Dispositivos</h2>
      </template>

      <div v-if="devicesPending" class="space-y-3">
        <div v-for="n in 3" :key="n" class="h-12 animate-pulse rounded-lg bg-elevated" />
      </div>

      <p v-else-if="!devices || devices.length === 0" class="py-6 text-center text-sm text-muted">
        Nenhum dispositivo registrado ainda. Rode o comando de instalação numa máquina do cliente.
      </p>

      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="text-left text-xs uppercase text-muted">
            <tr>
              <th class="px-4 py-2.5">Host / fingerprint</th>
              <th class="px-4 py-2.5">SO</th>
              <th class="px-4 py-2.5">Specs</th>
              <th class="px-4 py-2.5">Último contato</th>
              <th class="px-4 py-2.5">Status</th>
              <th class="px-4 py-2.5 text-right">Ações</th>
            </tr>
          </thead>
          <tbody>
            <DeviceRow
              v-for="d in devices"
              :key="d.id"
              :device="d"
              :heartbeat-interval="HEARTBEAT_INTERVAL"
              @approve="approve"
              @revoke="revoke"
            />
          </tbody>
        </table>
      </div>
    </UCard>
  </div>
</template>
