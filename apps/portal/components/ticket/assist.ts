// #1S — lógica pura do assistente de escrita de chamado por IA.
//
// A saída do LLM é tratada como RASCUNHO: apenas popula os campos do formulário
// (title/body), que o cliente edita e envia manualmente — NUNCA auto-submete. O
// texto é renderizado nos UInput/UTextarea (escapado por padrão; sem v-html).

export interface AssistResult {
  title: string
  body: string
}

export interface DraftForm {
  title: string
  body: string
}

/**
 * Botão "Melhorar com IA" só aparece quando a feature está ligada
 * (meta.ai_assist_enabled) E há texto de descrição para reescrever.
 */
export function shouldShowAssistButton(
  aiAssistEnabled: boolean | undefined,
  body: string,
): boolean {
  return Boolean(aiAssistEnabled) && body.trim().length > 0
}

/**
 * Aplica o rascunho retornado pela IA ao formulário. Title vazio na resposta
 * mantém o título atual (failure-safe). Não toca nenhum outro campo.
 */
export function applyAssistResult(form: DraftForm, result: AssistResult): void {
  if (result.title && result.title.trim()) form.title = result.title
  form.body = result.body
}
