<script setup lang="ts">
const username = ref('')
const password = ref('')
const error = ref('')

async function submit() {
  error.value = ''
  const res = await $fetch<{ ok: boolean, status?: number }>(
    '/api/auth/login',
    { method: 'POST', body: { username: username.value, password: password.value } },
  ).catch(() => ({ ok: false }))
  if (res.ok) await navigateTo('/')
  else error.value = 'Credenciais inválidas ou serviço indisponível.'
}
</script>

<template>
  <form class="max-w-sm mx-auto space-y-4" @submit.prevent="submit">
    <h1 class="text-xl font-bold">Entrar</h1>
    <input v-model="username" placeholder="Usuário" class="border w-full p-2 rounded">
    <input v-model="password" type="password" placeholder="Senha" class="border w-full p-2 rounded">
    <button
      type="submit" class="text-white px-4 py-2 rounded"
      :style="{ background: 'var(--brand-accent)' }">Entrar</button>
    <p v-if="error" class="text-red-600 text-sm">{{ error }}</p>
  </form>
</template>
