// R13b — regras dos checklists na interface. Lógica PURA.
//
// *"Temos aqui configurações de feriados, checklists personalizáveis."* (08:16)

export interface ChecklistItem {
  id: string
  text: string
  done: boolean
  done_by: string | null
  done_at: string | null
}

export interface Checklist {
  id: string
  template_name: string
  applied_by: string
  applied_at: string
  total: number
  done: number
  percent: number
  items: ChecklistItem[]
}

export interface ChecklistTemplate {
  id: string
  name: string
  description: string | null
  active: boolean
  items: string[]
}

/** Progresso local, para a barra andar antes da resposta do servidor voltar. */
export function localPercent(items: ChecklistItem[]): number {
  if (!items.length) return 0
  return Math.round((items.filter(i => i.done).length * 100) / items.length)
}

/**
 * Erros do cadastro de modelo. Lista vazia = pode salvar.
 *
 * O texto dos itens chega da tela como um bloco só, uma linha por item — é
 * como a pessoa escreve um procedimento, e evita um formulário com botão de
 * "adicionar item" para cada linha.
 */
export function validateTemplate(name: string, itemsText: string): string[] {
  const errors: string[] = []
  if (!name.trim()) errors.push('Dê um nome ao modelo.')
  if (!parseItems(itemsText).length) {
    // Modelo vazio só é descoberto depois de aplicado a um chamado.
    errors.push('Escreva pelo menos um item — um por linha.')
  }
  return errors
}

/** Uma linha, um item. Linhas em branco somem; a ordem é preservada. */
export function parseItems(itemsText: string): string[] {
  return itemsText
    .split('\n')
    .map(l => l.replace(/^\s*[-*•]\s*/, '').trim())
    .filter(Boolean)
}

/** Modelos que ainda não foram aplicados a este chamado. */
export function availableTemplates(
  templates: ChecklistTemplate[],
  applied: Checklist[],
): ChecklistTemplate[] {
  const used = new Set(applied.map(c => c.template_name))
  return templates.filter(t => t.active && !used.has(t.name))
}
