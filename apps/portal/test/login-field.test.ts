// O campo de identificação do login NÃO pode ser `type="email"`.
//
// Por que este teste existe: o Znuny autentica o cliente tanto pelo e-mail quanto
// pelo login (`eduardo.salvi`), mas o campo estava como `type="email"` — e a
// validação nativa do navegador barrava o envio do login curto ANTES de qualquer
// requisição sair. O usuário tinha uma credencial perfeitamente válida e recebia
// só um balão do browser, sem erro do servidor, sem log, sem nada para investigar.
//
// É um bug de uma palavra, invisível em teste de backend (o servidor nunca é
// chamado) e caro de diagnosticar. Este guard trava a regressão.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const loginPage = readFileSync(resolve(__dirname, '../pages/login.vue'), 'utf-8')

describe('campo de identificação do login (portal)', () => {
  it('não usa type="email" — barraria o login curto no navegador', () => {
    const identifierField = loginPage.slice(
      loginPage.indexOf('v-model="state.username"'),
      loginPage.indexOf('name="password"'),
    )
    expect(identifierField).not.toContain('type="email"')
    expect(identifierField).toContain('type="text"')
  })

  it('o rótulo avisa que aceita os dois formatos', () => {
    expect(loginPage).toMatch(/label="E-mail ou usuário"/)
  })
})
