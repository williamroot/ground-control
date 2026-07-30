// O campo de identificação do login do console NÃO pode ser `type="email"`.
//
// Mesmo motivo do guard equivalente no portal: o console aceita e-mail OU login de
// agente (`william`, `root@localhost`), e `type="email"` faria o navegador barrar
// o login curto antes de qualquer requisição sair — credencial válida, erro
// nenhum no servidor, nada para investigar.
//
// Aqui o risco é maior que no portal: existe agente sem e-mail cadastrado
// (`root@localhost`, criado pelo instalador do Znuny), para quem o login curto é
// o ÚNICO caminho de entrada.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const loginPage = readFileSync(resolve(__dirname, '../pages/login.vue'), 'utf-8')

describe('campo de identificação do login (console)', () => {
  it('não usa type="email" — há agente que só entra por login curto', () => {
    const identifierField = loginPage.slice(
      loginPage.indexOf('v-model="state.login"'),
      loginPage.indexOf('name="password"'),
    )
    expect(identifierField).not.toContain('type="email"')
    expect(identifierField).toContain('type="text"')
  })

  it('o rótulo avisa que aceita os dois formatos', () => {
    expect(loginPage).toMatch(/label="E-mail ou login"/)
  })
})
