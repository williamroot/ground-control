<script setup lang="ts">
// Donut SVG puro, SSR-safe (viewBox fixo, useId, sem window). Uma <path> (arco)
// por fatia, proporcional à soma. Zero deps externas (SVG nativo — mount-safe).
//
// palette:
//   'brand'    -> tons da cor de marca (identidade) — default.
//   'semantic' -> cores SEMÂNTICAS por fatia via `tone` (H8): estados como
//                 SLA estourado=error, em risco=warning, ok=success NUNCA usam
//                 a cor de marca.
type Tone = 'error' | 'warning' | 'success' | 'info' | 'neutral'
interface Segment { label: string, value: number, tone?: Tone }

const props = withDefaults(defineProps<{
  segments: Segment[]
  palette?: 'brand' | 'semantic'
  size?: number
  thickness?: number
}>(), { palette: 'brand', size: 160, thickness: 26 })

const gid = useId()

const TONE_VAR: Record<Tone, string> = {
  error: 'var(--color-error)',
  warning: 'var(--color-warning)',
  success: 'var(--color-success)',
  info: 'var(--color-info)',
  neutral: 'var(--color-neutral)',
}

// brand identity ramp: same hue, decreasing opacity per slice.
const BRAND_OPACITY = [1, 0.78, 0.58, 0.42, 0.3, 0.22]

function colorFor(seg: Segment, i: number): { fill: string, opacity: number } {
  if (props.palette === 'semantic') {
    return { fill: TONE_VAR[seg.tone ?? 'neutral'], opacity: 1 }
  }
  return { fill: 'var(--brand-primary)', opacity: BRAND_OPACITY[i % BRAND_OPACITY.length] }
}

function polar(cx: number, cy: number, r: number, frac: number): [number, number] {
  // frac in [0,1]; 0 at 12 o'clock, clockwise.
  const a = frac * 2 * Math.PI - Math.PI / 2
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)]
}

const arcs = computed(() => {
  const segs = props.segments
  const total = segs.reduce((acc, s) => acc + Math.max(0, s.value), 0)
  if (!segs.length || total <= 0) return []
  const cx = props.size / 2
  const cy = props.size / 2
  const rOuter = props.size / 2
  const rInner = rOuter - props.thickness
  let acc = 0
  return segs.map((seg, i) => {
    const frac = Math.max(0, seg.value) / total
    const start = acc
    const end = acc + frac
    acc = end
    const { fill, opacity } = colorFor(seg, i)
    // Fatia única de 100%: o arco de 360° tem início == fim (ponto das 12h) e
    // degenera (nada é desenhado). Desenha um ANEL completo (dois semicírculos
    // externos + dois internos) com fill-rule evenodd p/ vazar o miolo.
    if (frac >= 0.999999) {
      const d = [
        `M${cx},${(cy - rOuter).toFixed(2)}`,
        `A${rOuter},${rOuter} 0 1 1 ${cx},${(cy + rOuter).toFixed(2)}`,
        `A${rOuter},${rOuter} 0 1 1 ${cx},${(cy - rOuter).toFixed(2)}`,
        'Z',
        `M${cx},${(cy - rInner).toFixed(2)}`,
        `A${rInner},${rInner} 0 1 1 ${cx},${(cy + rInner).toFixed(2)}`,
        `A${rInner},${rInner} 0 1 1 ${cx},${(cy - rInner).toFixed(2)}`,
        'Z',
      ].join(' ')
      return { d, fill, opacity, label: seg.label, value: seg.value, ring: true }
    }
    const large = frac > 0.5 ? 1 : 0
    const [ox1, oy1] = polar(cx, cy, rOuter, start)
    const [ox2, oy2] = polar(cx, cy, rOuter, end)
    const [ix2, iy2] = polar(cx, cy, rInner, end)
    const [ix1, iy1] = polar(cx, cy, rInner, start)
    // donut wedge: outer arc clockwise, line in, inner arc counter-clockwise.
    const d = [
      `M${ox1.toFixed(2)},${oy1.toFixed(2)}`,
      `A${rOuter},${rOuter} 0 ${large} 1 ${ox2.toFixed(2)},${oy2.toFixed(2)}`,
      `L${ix2.toFixed(2)},${iy2.toFixed(2)}`,
      `A${rInner},${rInner} 0 ${large} 0 ${ix1.toFixed(2)},${iy1.toFixed(2)}`,
      'Z',
    ].join(' ')
    return { d, fill, opacity, label: seg.label, value: seg.value, ring: false }
  })
})
</script>

<template>
  <div v-if="!arcs.length" class="flex h-40 items-center justify-center text-sm text-dimmed">
    Sem dados no período
  </div>
  <svg
    v-else
    :viewBox="`0 0 ${size} ${size}`"
    preserveAspectRatio="xMidYMid meet"
    class="h-40 w-40"
    role="img"
    :aria-labelledby="gid"
  >
    <title :id="gid">Distribuição proporcional</title>
    <path
      v-for="(a, i) in arcs"
      :key="i"
      :d="a.d"
      :fill="a.fill"
      :fill-opacity="a.opacity"
      :fill-rule="a.ring ? 'evenodd' : undefined"
    >
      <title>{{ a.label }}: {{ a.value }}</title>
    </path>
  </svg>
</template>
