<script setup lang="ts">
const props = withDefaults(defineProps<{
  percent: number | null
  overage?: boolean
}>(), { overage: false })

const clamped = computed(() => {
  const p = props.percent
  if (p == null || Number.isNaN(p)) return 0
  return Math.max(0, Math.min(100, p))
})
</script>

<template>
  <div class="h-2 w-full overflow-hidden rounded-full bg-elevated">
    <div
      class="h-full rounded-full transition-all"
      :class="overage ? 'opacity-90' : ''"
      :style="{ width: `${clamped}%`, background: 'var(--brand-primary)' }"
    />
  </div>
</template>
