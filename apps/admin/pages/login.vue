<script setup lang="ts">
// Placeholder da Fase 0 — T1.E implementa o login de agente (cookie gsid_adm).
import { ADMIN_IDENTITY } from '#shared/identity'
</script>

<template>
  <div class="flex min-h-screen items-center justify-center px-4">
    <div class="w-full max-w-sm rounded-2xl border border-default bg-default p-8 text-center shadow-sm">
      <span class="mx-auto mb-4 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-lg font-bold text-white font-display">G</span>
      <h1 class="font-display text-xl font-bold">
        {{ ADMIN_IDENTITY.display_name }}
      </h1>
      <p class="mt-2 text-sm text-muted">
        Login de agente — em construção (T1.E).
      </p>
    </div>
  </div>
</template>
