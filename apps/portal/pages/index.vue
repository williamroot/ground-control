<script setup lang="ts">
interface Saldo { kind: string, remaining: number | null }
interface ContractItem {
  code: string, type: string, status: string
  starts_on: string, ends_on: string, saldo: Saldo
}

const headers = useRequestHeaders(['cookie'])
const { data: me } = await useAsyncData('me', () =>
  $fetch('/api/portal/me', { headers }).catch(() => null))
if (!me.value) await navigateTo('/login')

const { data: contracts } = await useAsyncData('contracts', () =>
  $fetch<ContractItem[]>('/api/portal/contracts', { headers })
    .catch(() => [] as ContractItem[]))
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-bold">Seus contratos</h1>
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left border-b">
          <th>Código</th><th>Tipo</th><th>Status</th><th>Saldo</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in contracts" :key="c.code" class="border-b">
          <td>{{ c.code }}</td><td>{{ c.type }}</td><td>{{ c.status }}</td>
          <td>{{ c.saldo.remaining ?? '—' }} {{ c.saldo.kind }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
