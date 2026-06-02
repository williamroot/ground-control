<script setup lang="ts">
interface Point { bucket: string, value: number }
const props = withDefaults(defineProps<{
  points: Point[]
  height?: number
  width?: number
}>(), { height: 120, width: 480 })

// Deterministic gradient id (SSR-safe, stable across server+client — H6).
const gid = useId()

const path = computed(() => {
  const pts = props.points
  if (!pts.length) return { area: '', line: '' }
  const w = props.width
  const h = props.height
  const max = Math.max(1, ...pts.map(p => p.value))
  const stepX = pts.length > 1 ? w / (pts.length - 1) : 0
  const xy = pts.map((p, i) => {
    const x = i * stepX
    const y = h - (p.value / max) * h
    return [x, y] as const
  })
  const line = xy.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`).join(' ')
  const area = `${line} L${w.toFixed(2)},${h} L0,${h} Z`
  return { area, line }
})
</script>

<template>
  <div v-if="!points.length" class="flex h-[120px] items-center justify-center text-sm text-dimmed">
    Sem dados de consumo no período
  </div>
  <svg
    v-else
    :viewBox="`0 0 ${width} ${height}`"
    preserveAspectRatio="none"
    class="h-32 w-full"
    role="img"
    aria-label="Consumo ao longo do tempo"
  >
    <defs>
      <linearGradient :id="gid" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--brand-primary)" stop-opacity="0.35" />
        <stop offset="100%" stop-color="var(--brand-primary)" stop-opacity="0" />
      </linearGradient>
    </defs>
    <path :d="path.area" :fill="`url(#${gid})`" />
    <path :d="path.line" fill="none" stroke="var(--brand-primary)" stroke-width="2" vector-effect="non-scaling-stroke" />
  </svg>
</template>
