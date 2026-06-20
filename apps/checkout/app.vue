<template>
  <UApp>
    <div class="min-h-screen bg-default">
      <header class="border-b border-default bg-default/80 backdrop-blur">
        <div class="mx-auto flex max-w-4xl items-center gap-2.5 px-5 py-4">
          <img src="/favicon.svg" alt="Gerti" class="h-8 w-8 rounded-lg">
          <span class="font-display text-lg font-extrabold tracking-tight text-highlighted">
            Gerti · Contratação
          </span>
        </div>
      </header>
      <NuxtPage />
      <footer class="mx-auto max-w-4xl px-5 py-10 text-center text-xs text-dimmed">
        Pagamentos processados via Asaas · Desenvolvido por WAS Soluções em Tecnologia
      </footer>
    </div>
  </UApp>
</template>
