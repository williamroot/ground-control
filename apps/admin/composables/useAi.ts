// Helpers de IA do console (#1N): descobre se a feature está ligada e dispara
// resumo / sugestão de resposta via os proxies server-side (que falam com o
// sidecar). A saída é texto (rascunho/resumo) — nunca ação automática.

export interface AiResult {
  kind: 'summary' | 'reply'
  text: string
}

// Flag opt-in: GET leve /api/admin/ai/enabled (dedupe por key).
export function useAiEnabled() {
  const headers = import.meta.server ? useRequestHeaders(['cookie']) : undefined
  return useAsyncData<boolean>('admin-ai-enabled', () =>
    $fetch<{ enabled: boolean }>('/api/admin/ai/enabled', { headers })
      .then(r => !!r?.enabled)
      .catch(() => false))
}

// Estado reativo de uma geração (loading/erro/resultado) p/ um ticket.
export function useAi(ticketId: number) {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const result = ref<AiResult | null>(null)

  function _message(status: number): string {
    if (status === 404) return 'Recurso de IA indisponível.'
    if (status === 503) return 'Serviço de IA temporariamente indisponível. Tente novamente.'
    return 'Falha ao gerar com IA.'
  }

  async function _run(path: string, kind: AiResult['kind'], extra?: Record<string, unknown>) {
    loading.value = true
    error.value = null
    try {
      const data = await $fetch<{ text: string }>(path, {
        method: 'POST',
        body: { ticket_id: ticketId, ...(extra ?? {}) },
      })
      result.value = { kind, text: data.text }
    }
    catch (e: unknown) {
      const status = (e as { statusCode?: number, status?: number })?.statusCode
        ?? (e as { status?: number })?.status ?? 0
      error.value = _message(status)
      result.value = null
    }
    finally {
      loading.value = false
    }
  }

  const summarize = () => _run('/api/admin/ai/summarize', 'summary')
  const suggestReply = (instruction?: string) =>
    _run('/api/admin/ai/suggest-reply', 'reply', instruction ? { instruction } : undefined)

  return { loading, error, result, summarize, suggestReply }
}
