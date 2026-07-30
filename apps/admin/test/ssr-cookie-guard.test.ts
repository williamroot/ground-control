// Toda página do console que busca dados no SSR precisa repassar o cookie.
//
// Por que este teste existe: `/atendimento` chamava `$fetch('/api/admin/tickets')`
// sem `headers`. No SSR — carga direta da rota ou F5 — o fetch interno do Nitro
// NÃO herda o cookie do navegador, então a requisição saía sem sessão, o sidecar
// devolvia 401 e a tela mostrava "Não foi possível carregar os chamados" com o
// backend perfeitamente saudável.
//
// O que torna esse bug caro: navegando por dentro do app o cookie vai junto e
// tudo parece certo. Só o acesso direto quebra — que é justamente como o operador
// abre a página quando alguém manda o link. É a mesma classe do fix 039ebb8 no
// portal.
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const PAGES = resolve(__dirname, '../pages')

function vueFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return vueFiles(full)
    return full.endsWith('.vue') ? [full] : []
  })
}

// `$fetch` dentro de `useAsyncData` roda no SSR e precisa de `headers`.
// POST disparado por clique roda só no navegador, que já manda o cookie sozinho.
const SSR_FETCH = /useAsyncData[\s\S]{0,400}?\$fetch<?[^>]*>?\(\s*'(\/api\/[^']+)'\s*,\s*\{([\s\S]{0,300}?)\}/g

describe('páginas do console: fetch de SSR repassa o cookie', () => {
  const offenders: string[] = []

  for (const file of vueFiles(PAGES)) {
    const source = readFileSync(file, 'utf-8')
    for (const match of source.matchAll(SSR_FETCH)) {
      if (!match[2].includes('headers')) {
        offenders.push(`${relative(PAGES, file)} -> ${match[1]}`)
      }
    }
  }

  it('nenhuma chamada de useAsyncData sem headers', () => {
    expect(offenders, `sem cookie no SSR (a tela cai em erro no acesso direto):\n${offenders.join('\n')}`)
      .toEqual([])
  })
})
