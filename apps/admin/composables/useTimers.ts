// Estado compartilhado dos timers do agente (#1J fase 3). O servidor (sidecar) é
// a fonte da verdade: carregamos os timers ativos de GET /api/admin/timer/active
// e re-sincronizamos após cada ação. Um ÚNICO setInterval(1000) atualiza o ref
// `now`, que dirige o display "tique-taque" reativo em todas as telas que
// consomem este composable (lista + detalhe veem o MESMO timer).

export interface Timer {
  id: string
  znuny_ticket_id: number
  status: 'running' | 'paused'
  accumulated_seconds: number
  last_started_at: string | null
  committed_time_unit: string | null
}

export interface StopPayload {
  timer_id: string
  adjust_minutes: number
  note: string
}

// Epoch (segundos) de um timestamp ISO do sidecar. Trata null/ inválido como 0.
function epochSeconds(iso: string | null): number {
  if (!iso) return 0
  const ms = Date.parse(iso)
  return Number.isNaN(ms) ? 0 : ms / 1000
}

export function useTimers() {
  // Mapa znuny_ticket_id -> timer, compartilhado por toda a app (useState).
  const timers = useState<Record<number, Timer>>('timers', () => ({}))
  const loading = useState<boolean>('timers-loading', () => false)
  // Relógio reativo: um único interval global o avança de segundo em segundo.
  const now = useState<number>('timers-now', () => Date.now())

  const activeCount = computed(() =>
    Object.keys(timers.value).length)

  function timerFor(ticketId: number): Timer | undefined {
    return timers.value[ticketId]
  }

  // Segundos decorridos: acumulado + (se rodando) o tempo desde last_started_at.
  // Depende de `now` para recomputar a cada segundo enquanto roda.
  function elapsed(timer: Timer): number {
    let total = timer.accumulated_seconds
    if (timer.status === 'running' && timer.last_started_at) {
      const delta = now.value / 1000 - epochSeconds(timer.last_started_at)
      total += Math.max(0, delta)
    }
    return Math.floor(total)
  }

  // HH:MM:SS (zero-padded), tabular para não "pular" largura ao ticar.
  function formatHMS(totalSeconds: number): string {
    const s = Math.max(0, Math.floor(totalSeconds))
    const hh = Math.floor(s / 3600)
    const mm = Math.floor((s % 3600) / 60)
    const ss = s % 60
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${pad(hh)}:${pad(mm)}:${pad(ss)}`
  }

  async function refresh(): Promise<void> {
    loading.value = true
    try {
      const list = await $fetch<Timer[] | null>('/api/admin/timer/active')
      const next: Record<number, Timer> = {}
      for (const t of list ?? []) next[t.znuny_ticket_id] = t
      timers.value = next
    }
    catch {
      // Mantém o estado anterior em falha de rede — não derruba o display.
    }
    finally {
      loading.value = false
    }
  }

  async function start(znunyTicketId: number): Promise<void> {
    await $fetch('/api/admin/timer/start', {
      method: 'POST',
      body: { znuny_ticket_id: znunyTicketId },
    })
    await refresh()
  }

  async function pause(timerId: string): Promise<void> {
    await $fetch('/api/admin/timer/pause', {
      method: 'POST',
      body: { timer_id: timerId },
    })
    await refresh()
  }

  async function resume(timerId: string): Promise<void> {
    await $fetch('/api/admin/timer/resume', {
      method: 'POST',
      body: { timer_id: timerId },
    })
    await refresh()
  }

  async function stop(payload: StopPayload): Promise<void> {
    await $fetch('/api/admin/timer/stop', {
      method: 'POST',
      body: payload,
    })
    await refresh()
  }

  // Liga o relógio global UMA vez (no cliente). Reaproveitado por quem montar.
  function useTicker(): void {
    if (!import.meta.client) return
    onMounted(() => {
      const handle = useState<ReturnType<typeof setInterval> | null>('timers-interval', () => null)
      if (handle.value) return
      handle.value = setInterval(() => {
        now.value = Date.now()
      }, 1000)
    })
  }

  return {
    timers,
    loading,
    now,
    activeCount,
    timerFor,
    elapsed,
    formatHMS,
    refresh,
    start,
    pause,
    resume,
    stop,
    useTicker,
  }
}
