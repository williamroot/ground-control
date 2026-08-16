// Guard de mês dos proxies de relatório (Onda 3, R18b).
//
// Vive em `server/utils` porque o escopo de auto-import do nitro é separado do
// dos `composables/` — o `isValidMonth` da tela não existe aqui. Nome diferente
// de propósito, para não parecer a mesma função em dois lugares: esta é a
// guarda do proxy, aquela é o feedback imediato do formulário.
//
// Defesa em profundidade: o sidecar também recusa `2026-13` com 422. Recusar
// aqui economiza um round-trip e impede que mês malformado chegue a virar
// query string.
export function isReportMonth(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}$/.test(value)) return false
  const year = Number(value.slice(0, 4))
  const month = Number(value.slice(5))
  return month >= 1 && month <= 12 && year >= 2000 && year <= 2100
}
