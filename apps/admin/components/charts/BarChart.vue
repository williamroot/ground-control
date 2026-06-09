<script setup lang="ts">
// SVG puro, SSR-safe (viewBox fixo, preserveAspectRatio, sem window). Uma <rect>
// por barra; cor de marca (var(--brand-primary)) — identidade. Zero deps externas
// (sem U*/@nuxt/icon: charts são SVG nativo — lição #1M/#1N para mount em testes).
interface Bar { label: string, value: number }
const props = withDefaults(defineProps<{
  bars: Bar[]
  height?: number
  width?: number
}>(), { height: 120, width: 480 })

const gid = useId()

const layout = computed(() => {
  const bars = props.bars
  const w = props.width
  const h = props.height
  const n = bars.length
  if (!n) return []
  const max = Math.max(1, ...bars.map(b => b.value))
  const gap = w * 0.04
  const slot = w / n
  const bw = Math.max(1, slot - gap)
  return bars.map((b, i) => {
    const value = Math.max(0, b.value)
    // min visible height so zero/low bars still render a rect (and a count).
    const bh = value === 0 ? 1 : Math.max(2, (value / max) * h)
    return {
      x: i * slot + gap / 2,
      y: h - bh,
      width: bw,
      height: bh,
      label: b.label,
      value: b.value,
    }
  })
})
</script>

<template>
  <div v-if="!bars.length" class="flex h-[120px] items-center justify-center text-sm text-dimmed">
    Sem dados no período
  </div>
  <svg
    v-else
    :viewBox="`0 0 ${width} ${height}`"
    preserveAspectRatio="none"
    class="h-32 w-full"
    role="img"
    :aria-labelledby="gid"
  >
    <title :id="gid">Distribuição por categoria</title>
    <rect
      v-for="(r, i) in layout"
      :key="i"
      :x="r.x"
      :y="r.y"
      :width="r.width"
      :height="r.height"
      rx="2"
      fill="var(--brand-primary)"
    >
      <title>{{ r.label }}: {{ r.value }}</title>
    </rect>
  </svg>
</template>
