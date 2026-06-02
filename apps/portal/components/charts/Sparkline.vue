<script setup lang="ts">
interface Point { bucket: string, value: number }
const props = withDefaults(defineProps<{ points: Point[] }>(), { points: () => [] })
const line = computed(() => {
  const pts = props.points
  if (!pts.length) return ''
  const w = 120
  const h = 28
  const max = Math.max(1, ...pts.map(p => p.value))
  const stepX = pts.length > 1 ? w / (pts.length - 1) : 0
  return pts.map((p, i) => {
    const x = i * stepX
    const y = h - (p.value / max) * h
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
})
</script>

<template>
  <svg v-if="points.length" viewBox="0 0 120 28" preserveAspectRatio="none" class="h-7 w-full" aria-hidden="true">
    <path :d="line" fill="none" stroke="var(--brand-primary)" stroke-width="1.5" vector-effect="non-scaling-stroke" />
  </svg>
  <div v-else class="h-7" />
</template>
