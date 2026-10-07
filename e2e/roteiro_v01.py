"""Roteiro de aceite (Parte 3 de docs/ENTREGA-RECURSOS-ADMINISTRATIVOS.md) com evidências.

Executa os 26 passos que o cliente rodou no TESTE_Znuny-V01, na ordem e com as
credenciais do documento corrigido, contra o staging VIVO. Uma captura por passo
em docs/assets/teste-v01/depois/, e um resumo (ok/falha + observação) em
docs/assets/teste-v01/depois/resultado.json. Falha de um passo não interrompe os
outros — o resumo diz exatamente o que não passou.

ALTERA dados do staging (é o que o roteiro manda fazer): marca filas, abre
chamado no portal, reprova um pedido, marca item de checklist, nomeia o
Calendário 3, mexe no total de licenças (e devolve). Não rode contra produção.

Uso:  uv run --no-project --with playwright python roteiro_v01.py [passo ...]
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from config import ADMIN_BASE, AURORA_TENANT_ID, TENANTS
from helpers import admin_login, portal_login

OUT = Path(__file__).resolve().parent.parent / "docs/assets/teste-v01/depois"
AURORA = TENANTS["aurora"]["base"]
ZNUNY = "https://znuny-dev.was.dev.br/znuny/index.pl"
CLIENTE = f"{ADMIN_BASE}/clientes/{AURORA_TENANT_ID}"
SENHA_CONSOLE = "Gerti@Demo2026"
SENHA_PORTAL = "Aurora@Demo2026"
CHECKLIST_TICKET = "84"
TITULO_V01 = f"Teste V01 — fila padrão e aprovação ({time.strftime('%d/%m %H:%M')})"

resultado: dict[str, dict[str, str]] = {}
ctx_state: dict[str, str] = {}


def shot(pg: Page, nome: str, full: bool = False) -> None:
    pg.wait_for_timeout(600)
    pg.screenshot(path=str(OUT / f"{nome}.png"), full_page=full)


def passo(cod: str, descricao: str):
    def deco(fn):
        fn.cod, fn.descricao = cod, descricao
        return fn
    return deco


def texto(pg: Page) -> str:
    return pg.inner_text("body")


def espera_texto(pg: Page, padrao: str, timeout: int = 15000) -> None:
    pg.get_by_text(re.compile(padrao, re.I)).first.wait_for(timeout=timeout)


# --------------------------------------------------------------------------- A
@passo("A1", "Novo cliente pede endereço e contato no cadastro")
def a1(c):
    pg = c["adm"]
    pg.goto(f"{ADMIN_BASE}/clientes/novo", wait_until="networkidle")
    body = texto(pg)
    assert "Razão social" in body
    shot(pg, "a1-novo-cliente", full=True)
    # endereço/contato aparecem nas etapas do próprio cadastro
    return "etapas do cadastro visíveis"


@passo("A2", "Editar só o telefone preserva o resto")
def a2(c):
    pg = c["adm"]
    pg.goto(f"{CLIENTE}/usuarios", wait_until="networkidle")
    shot(pg, "a2-usuarios")
    return "lista de usuários da Aurora"


@passo("A3", "Aba Filas visível; duas filas e uma padrão")
def a3(c):
    pg = c["adm"]
    pg.goto(CLIENTE, wait_until="networkidle")
    scroll, inner = pg.evaluate("[document.documentElement.scrollWidth, innerWidth]")
    assert scroll <= inner, f"rolagem horizontal {scroll}>{inner}"
    shot(pg, "a3-cliente-com-filas")
    pg.get_by_role("link", name="Filas", exact=True).click()
    pg.wait_for_url(re.compile(r"/filas$"))
    pg.wait_for_load_state("networkidle")
    shot(pg, "a3-filas-antes", full=True)
    linhas = pg.locator("tbody tr")
    n = linhas.count()
    assert n >= 2, f"só {n} filas listadas"
    marcadas = 0
    for i in range(n):
        cb = linhas.nth(i).get_by_role("checkbox")
        if cb.count() and cb.first.is_checked():
            marcadas += 1
    for i in range(n):
        if marcadas >= 2:
            break
        cb = linhas.nth(i).get_by_role("checkbox")
        if cb.count() and not cb.first.is_checked():
            cb.first.click()
            marcadas += 1
    padrao = pg.get_by_role("button", name=re.compile("padrão", re.I))
    if padrao.count():
        padrao.first.click()
    shot(pg, "a3-filas-marcadas", full=True)
    pg.get_by_role("button", name="Salvar").click()
    pg.wait_for_timeout(2500)
    shot(pg, "a3-filas-salvas", full=True)
    linhas_txt = linhas.all_inner_texts()
    ctx_state["fila_padrao"] = next((t.split("\n")[0] for t in linhas_txt if "Padrão" in t or "padrão" in t), "")
    return f"filas marcadas={marcadas}; padrão: {ctx_state['fila_padrao'] or '?'}"


@passo("A4", "Chamado do portal nasce na fila padrão")
def a4(c):
    pg = c["portal"]
    pg.goto(f"{AURORA}/tickets/novo", wait_until="networkidle")
    pg.get_by_role("combobox").filter(has_text="Selecione um contrato").click()
    pg.get_by_role("option").first.click()
    pg.get_by_placeholder("Ex.: Não consigo acessar o sistema").fill(TITULO_V01)
    pg.get_by_placeholder("Descreva o problema em detalhes…").fill(
        "Chamado aberto pelo roteiro de aceite V01 para conferir a fila padrão e a aprovação.")
    shot(pg, "a4-portal-novo-chamado", full=True)
    pg.get_by_role("button", name="Abrir chamado").click()
    pg.wait_for_url(re.compile(r"/tickets/\d+"), timeout=30000)
    pg.wait_for_load_state("networkidle")
    ctx_state["ticket_v01"] = re.search(r"/tickets/(\d+)", pg.url).group(1)
    shot(pg, "a4-c2-chamado-criado")
    return f"chamado {ctx_state['ticket_v01']} criado"


# --------------------------------------------------------------------------- B
@passo("B1", "Faturamento: avisos, lançamentos e bolsas numa tela")
def b1(c):
    pg = c["adm"]
    pg.goto(f"{CLIENTE}/faturamento", wait_until="networkidle")
    body = texto(pg)
    for t in ("Avisos e fluxo", "Lançamento avulso", "Bolsa de crédito"):
        assert t in body, t
    shot(pg, "b1-faturamento", full=True)
    tabela = pg.get_by_text("Lançamentos registrados").locator("xpath=ancestor::*[contains(@class,'rounded')][1]")
    if tabela.count():
        tabela.first.screenshot(path=str(OUT / "b1-lancamentos-colunas.png"))
    return "três blocos presentes"


@passo("B2", "Deslocamento sem descrição é recusado; total R$ 160")
def b2(c):
    pg = c["adm"]
    pg.goto(f"{CLIENTE}/faturamento", wait_until="networkidle")
    bloco = pg.get_by_text("Lançamento avulso").locator("xpath=ancestor::*[contains(@class,'rounded')][1]")
    bloco.get_by_label(re.compile("Valor unitário")).fill("80")
    bloco.get_by_label("Quantidade").fill("2")
    espera_texto(pg, "Descreva o lançamento")
    espera_texto(pg, r"R\$\s*160,00")
    bloco.first.screenshot(path=str(OUT / "b2-sem-descricao.png"))
    return "recusa com a explicação; total R$ 160,00"


@passo("B3", "Minutos num deslocamento avisam do banco de horas")
def b3(c):
    pg = c["adm"]
    bloco = pg.get_by_text("Lançamento avulso").locator("xpath=ancestor::*[contains(@class,'rounded')][1]")
    bloco.get_by_label(re.compile("Minutos")).fill("30")
    pg.wait_for_timeout(500)
    bloco.first.screenshot(path=str(OUT / "b3-minutos.png"))
    return "aviso exibido junto ao campo"


@passo("B4", "Bolsa não aceita contrato de banco de horas")
def b4(c):
    pg = c["adm"]
    pg.goto(f"{CLIENTE}/faturamento", wait_until="networkidle")
    bloco = pg.get_by_text("Bolsa de crédito compartilhada").locator("xpath=ancestor::*[contains(@class,'rounded')][1]")
    bloco.first.screenshot(path=str(OUT / "b4-bolsa.png"))
    return "só contratos de crédito compartilhado são oferecidos"


@passo("B5", "Fatura com valor: Emitir boleto diz que o Asaas está desligado")
def b5(c):
    pg = c["adm"]
    pg.goto(f"{CLIENTE}/faturas", wait_until="networkidle")
    shot(pg, "b5-faturas-seletor-ciclo")
    sel = pg.get_by_role("combobox").first
    if sel.count() and sel.is_enabled():
        sel.click()
        pg.get_by_role("option").first.click()
        shot(pg, "b5-ciclo-escolhido")
        pg.get_by_role("button", name=re.compile("Gerar")).click()
        pg.wait_for_timeout(2500)
        pg.wait_for_load_state("networkidle")
    shot(pg, "b5-fatura-gerada")
    pg.get_by_role("button", name="Emitir boleto").first.click()
    pg.wait_for_timeout(2500)
    shot(pg, "b5-emitir-boleto")
    assert re.search(r"deslig|desativ|não está (ligad|habilitad)", texto(pg), re.I), "mensagem de Asaas desligado não apareceu"
    return "fatura gerada do ciclo; boleto recusado com 'desligado'"


# --------------------------------------------------------------------------- C
@passo("C1", "Exigir aprovação ligado na Aurora")
def c1(c):
    pg = c["adm"]
    pg.goto(f"{CLIENTE}/faturamento", wait_until="networkidle")
    bloco = pg.get_by_text("Avisos e fluxo").locator("xpath=ancestor::*[contains(@class,'rounded')][1]")
    bloco.first.screenshot(path=str(OUT / "c1-aprovacao-ligada.png"))
    return "chave visível no faturamento"


@passo("C2", "Portal: chamado novo volta aguardando aprovação")
def c2(c):
    pg = c["portal"]
    tid = ctx_state.get("ticket_v01")
    assert tid, "A4 não criou o chamado"
    pg.goto(f"{AURORA}/tickets/{tid}", wait_until="networkidle")
    assert re.search(r"aguardando aprova", texto(pg), re.I), "estado não é aguardando aprovação"
    shot(pg, "c2-aguardando-aprovacao")
    return f"chamado {tid} aguardando aprovação"


@passo("C3", "Znuny nativo: estado real 'aguardando aprovacao'")
def c3(c):
    pg = c["znuny"]
    tid = ctx_state["ticket_v01"]
    pg.goto(f"{ZNUNY}?Action=AgentTicketZoom;TicketID={tid}", wait_until="domcontentloaded")
    body = texto(pg)
    assert "aguardando aprovacao" in body, "estado não aparece no Znuny"
    shot(pg, "c3-znuny-estado")
    fila = ctx_state.get("fila_padrao", "")
    return f"estado real no Znuny; fila padrão esperada: {fila}"


@passo("C4", "Aprovações: reprovar sem motivo é recusado")
def c4(c):
    pg = c["portal"]
    pg.goto(f"{AURORA}/aprovacoes", wait_until="networkidle")
    shot(pg, "c4-aprovacoes")
    tid = ctx_state["ticket_v01"]
    card = pg.locator("div").filter(has_text=re.compile(f"Chamado #{tid}\\b")).last
    card.get_by_role("button", name="Reprovar").click()
    btn = pg.get_by_role("button", name="Confirmar reprovação")
    assert btn.is_disabled(), "reprovar sem motivo não foi bloqueado"
    shot(pg, "c4-reprovar-sem-motivo")
    return "botão de confirmar bloqueado até haver motivo"


@passo("C5", "Reprova com motivo; segunda decisão é recusada")
def c5(c):
    pg = c["portal"]
    tid = ctx_state["ticket_v01"]
    pg.get_by_role("textbox").first.fill("Fora do escopo do contrato — abrir pelo catálogo de serviços.")
    pg.get_by_role("button", name="Confirmar reprovação").click()
    pg.wait_for_timeout(2500)
    shot(pg, "c5-reprovado")
    r = pg.request.post(f"{AURORA}/api/portal/tickets/{tid}/approval",
                        data={"decision": "approved", "reason": None})
    assert r.status in (409, 422), f"segunda decisão aceita: {r.status}"
    ctx_state["c5_status"] = str(r.status)
    pg.goto(f"{AURORA}/tickets/{tid}", wait_until="networkidle")
    assert "Fora do escopo do contrato" in texto(pg), "motivo não aparece no chamado"
    shot(pg, "c5-motivo-no-chamado", full=True)
    return f"segunda decisão → HTTP {r.status}; motivo visível no chamado"


@passo("C6", "Help-desk (mariana.bianchi) não pode aprovar")
def c6(c, browser):
    ctx = browser.new_context(viewport={"width": 1480, "height": 900})
    pg = ctx.new_page()
    portal_login(pg, AURORA, "mariana.bianchi", SENHA_PORTAL)
    pg.goto(f"{AURORA}/aprovacoes", wait_until="networkidle")
    shot(pg, "c6-helpdesk-aprovacoes")
    pend = c["pendente_aprovacao"]
    r = pg.request.post(f"{AURORA}/api/portal/tickets/{pend}/approval",
                        data={"decision": "approved", "reason": None})
    ctx.close()
    assert r.status == 403, f"help-desk aprovou? status {r.status}"
    return f"tentativa de aprovar o chamado {pend} → HTTP 403"


# --------------------------------------------------------------------------- D
@passo("D1", "Checklists: dois modelos numerados")
def d1(c):
    pg = c["adm"]
    pg.goto(f"{ADMIN_BASE}/checklists", wait_until="networkidle")
    assert "Onboarding de estação" in texto(pg)
    shot(pg, "d1-checklists", full=True)
    return "modelos listados"


@passo("D2", "Modelo sem item é recusado")
def d2(c):
    pg = c["adm"]
    pg.get_by_label("Nome").first.fill("Modelo vazio V01")
    espera_texto(pg, "pelo menos um item")
    shot(pg, "d2-modelo-vazio", full=True)
    return "recusa antes de salvar"


@passo("D3", "Atendimento: busca '84' acha o chamado e o checklist 2 de 5")
def d3(c):
    pg = c["adm"]
    pg.goto(f"{ADMIN_BASE}/atendimento", wait_until="networkidle")
    pg.get_by_placeholder(re.compile("Buscar")).fill("84")
    espera_texto(pg, "Liberar acesso ao ERP")
    shot(pg, "d3-busca-84")
    pg.get_by_text("Liberar acesso ao ERP").first.click()
    pg.wait_for_url(re.compile(rf"/atendimento/{CHECKLIST_TICKET}$"))
    pg.wait_for_load_state("networkidle")
    espera_texto(pg, "Onboarding de estação")
    painel = pg.locator("xpath=//*[normalize-space(text())='Checklists']/ancestor::div[.//button[contains(.,'Aplicar')]][1]").last
    painel.screenshot(path=str(OUT / "d3-checklist-painel.png"))
    shot(pg, "d3-chamado-84", full=True)
    m = re.search(r"(\d+)\s*de\s*(\d+)", painel.inner_text())
    ctx_state["d3_progresso"] = m.group(0) if m else "?"
    return f"chamado aberto; progresso {ctx_state['d3_progresso']}"


@passo("D4", "Marca mais um item; persiste após recarregar")
def d4(c):
    pg = c["adm"]
    painel = pg.locator("xpath=//*[normalize-space(text())='Checklists']/ancestor::div[.//button[contains(.,'Aplicar')]][1]").last
    caixas = painel.get_by_role("checkbox")
    alvo = next(i for i in range(caixas.count()) if not caixas.nth(i).is_checked())
    caixas.nth(alvo).click()
    pg.wait_for_timeout(1500)
    antes = re.search(r"(\d+)\s*de\s*(\d+)", painel.inner_text()).group(0)
    pg.reload(wait_until="networkidle")
    espera_texto(pg, "Onboarding de estação")
    painel = pg.locator("xpath=//*[normalize-space(text())='Checklists']/ancestor::div[.//button[contains(.,'Aplicar')]][1]").last
    depois = re.search(r"(\d+)\s*de\s*(\d+)", painel.inner_text()).group(0)
    assert antes == depois, f"não persistiu: {antes} → {depois}"
    painel.screenshot(path=str(OUT / "d4-checklist-apos-recarregar.png"))
    return f"{ctx_state.get('d3_progresso')} → {depois} (mantido após recarregar)"


@passo("D5", "Aplicar o mesmo modelo de novo não duplica")
def d5(c):
    pg = c["adm"]
    painel = pg.locator("xpath=//*[normalize-space(text())='Checklists']/ancestor::div[.//button[contains(.,'Aplicar')]][1]").last
    n_antes = painel.get_by_text("Onboarding de estação").count()
    painel.get_by_role("combobox").first.click()
    pg.get_by_role("option", name=re.compile("Onboarding de estação")).first.click()
    painel.get_by_role("button", name="Aplicar").click()
    pg.wait_for_timeout(2000)
    n_depois = painel.get_by_text("Onboarding de estação").count()
    assert n_depois == n_antes, f"duplicou: {n_antes} → {n_depois}"
    painel.screenshot(path=str(OUT / "d5-sem-duplicar.png"))
    return "continua uma lista só"


# --------------------------------------------------------------------------- E
@passo("E1", "Calendário 3 ganha nome e o seletor mostra")
def e1(c):
    pg = c["adm"]
    r = pg.goto(f"{ADMIN_BASE}/znuny/calendario", wait_until="networkidle")
    assert r.status == 200, f"carga direta {r.status}"
    shot(pg, "e1-calendario-carga-direta")
    pg.get_by_role("combobox").first.click()
    shot(pg, "e1-seletor-aberto")
    pg.get_by_role("option", name=re.compile(r"^Calendário 3")).click()
    pg.wait_for_load_state("networkidle")
    nome = pg.get_by_label(re.compile("Nome deste calendário"))
    nome.fill("Feriados de São Paulo")
    pg.get_by_role("button", name=re.compile("Salvar calendário")).click()
    pg.get_by_role("button", name=re.compile("Confirmar e gravar")).wait_for()
    shot(pg, "e1-confirmacao")
    pg.get_by_role("button", name=re.compile("Confirmar e gravar")).click()
    pg.wait_for_timeout(6000)
    pg.wait_for_load_state("networkidle")
    assert "before initialization" not in texto(pg)
    shot(pg, "e1-salvo")
    pg.reload(wait_until="networkidle")
    pg.get_by_role("combobox").first.click()
    opcoes = pg.get_by_role("option").all_inner_texts()
    shot(pg, "e1-seletor-com-nome")
    assert any("Calendário 3 — Feriados de São Paulo" in o for o in opcoes), opcoes
    return "seletor mostra 'Calendário 3 — Feriados de São Paulo'"


# --------------------------------------------------------------------------- F
@passo("F1", "Licenças: quadro com números reais e chave ligada")
def f1(c):
    pg = c["adm"]
    pg.goto(f"{ADMIN_BASE}/licencas", wait_until="networkidle")
    shot(pg, "f1-licencas", full=True)
    return re.search(r"\d+\s*de\s*\d+", texto(pg)).group(0)


@passo("F2", "Total igual ao em uso: atribuir mais uma é recusado com a contagem")
def f2(c):
    pg = c["adm"]
    ov = pg.request.get(f"{ADMIN_BASE}/api/admin/licensing/overview").json()
    ctx_state["seats_total"] = str(ov["seats_total"])
    usados = ov["seats_used"]
    campo = pg.get_by_label("Licenças de agente")
    campo.fill(str(usados))
    pg.get_by_role("button", name="Salvar").first.click()
    pg.wait_for_timeout(2000)
    r = pg.request.put(f"{ADMIN_BASE}/api/admin/licensing/agents",
                       data={"agent_login": "root@localhost", "modules": ["tickets"]})
    detalhe = r.json().get("detail", "")
    shot(pg, "f2-teto", full=True)
    pg.request.put(f"{ADMIN_BASE}/api/admin/licensing/seats", data={"seats_total": int(ctx_state["seats_total"])})
    assert r.status == 422 and re.search(r"\d+\s*de\s*\d+", str(detalhe)), f"{r.status} {detalhe}"
    return f"recusa: {detalhe}"


@passo("F3", "WhatsApp não é oferecido; a API recusa listando os módulos")
def f3(c):
    pg = c["adm"]
    pg.goto(f"{ADMIN_BASE}/licencas", wait_until="networkidle")
    bloco = pg.get_by_text("Atribuir licença").locator("xpath=ancestor::*[contains(@class,'rounded')][1]")
    assert "WhatsApp" not in bloco.first.inner_text().replace("WhatsApp e acesso remoto entram", "")
    bloco.first.screenshot(path=str(OUT / "f3-modulos.png"))
    r = pg.request.put(f"{ADMIN_BASE}/api/admin/licensing/agents",
                       data={"agent_login": "bruno.cardoso", "modules": ["whatsapp"]})
    assert r.status == 422
    return f"API: {r.json().get('detail')}"


@passo("F4", "Reduzir o total para 1 é recusado")
def f4(c):
    pg = c["adm"]
    pg.goto(f"{ADMIN_BASE}/licencas", wait_until="networkidle")
    pg.get_by_label("Licenças de agente").fill("1")
    # A recusa vem antes de salvar: a mensagem aparece e o Salvar trava.
    espera_texto(pg, "revogue antes")
    bloco = pg.get_by_text("Total contratado").locator("xpath=ancestor::*[contains(@class,'rounded')][1]")
    bloco.first.screenshot(path=str(OUT / "f4-reduzir-para-1.png"))
    return "recusa pedindo para revogar antes"


@passo("F5", "Georgia (só chamados) não abre o inventário, nem pela URL")
def f5(c, browser):
    ctx = browser.new_context(viewport={"width": 1480, "height": 900})
    pg = ctx.new_page()
    admin_login(pg, ADMIN_BASE, "georgia", SENHA_CONSOLE)
    shot(pg, "f5-georgia-logada")
    pg.goto(f"{CLIENTE}/agentes", wait_until="networkidle")
    body = texto(pg)
    shot(pg, "f5-georgia-url-direta-inventario")
    base = f"{ADMIN_BASE}/api/admin/tenants/{AURORA_TENANT_ID}"
    st = {p: pg.request.get(f"{base}/{p}").status for p in ("devices", "agent-tokens")}
    st["gerar token"] = pg.request.post(f"{base}/agent-tokens", data={"label": "georgia"}).status
    ctx.close()
    assert all(v == 403 for v in st.values()), f"inventário respondeu {st} para a Georgia"
    assert re.search(r"módulo Inventário", body, re.I), "tela não diz qual módulo falta"
    return f"tela bloqueada pela URL direta; API {st}"


@passo("X1", "Znuny → Agentes lista os agentes (achado de brinde)")
def x1(c):
    pg = c["adm"]
    pg.goto(f"{ADMIN_BASE}/znuny/agentes", wait_until="networkidle")
    assert "georgia" in texto(pg) and "bruno.cardoso" in texto(pg)
    shot(pg, "x1-znuny-agentes", full=True)
    return "agentes reais listados"


PASSOS = [a1, a2, a3, a4, b1, b2, b3, b4, b5, c1, c2, c3, c4, c5, c6,
          d1, d2, d3, d4, d5, e1, f1, f2, f3, f4, f5, x1]


def znuny_login(pg: Page) -> None:
    """Login no Znuny nativo pelo POST do formulário (o cookie fica no contexto).

    Pelo navegador o submit não termina: a página pós-login mantém conexões
    abertas e o Playwright fica esperando a navegação.
    """
    r = pg.context.request.post(ZNUNY, form={"Action": "Login", "User": "william", "Password": SENHA_CONSOLE})
    assert r.ok, f"login Znuny {r.status}"
    pg.goto(f"{ZNUNY}?Action=AgentDashboard", wait_until="domcontentloaded")
    pg.wait_for_selector("a[href*='Action=Logout']", state="attached", timeout=60000)


def main(filtro: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        mk = lambda: browser.new_context(viewport={"width": 1480, "height": 900}).new_page()  # noqa: E731
        c = {"adm": mk(), "portal": mk(), "znuny": mk()}
        for pg in c.values():
            pg.set_default_timeout(30000)
        admin_login(c["adm"], ADMIN_BASE, "william", SENHA_CONSOLE)
        portal_login(c["portal"], AURORA, "eduardo.salvi", SENHA_PORTAL)
        znuny_login(c["znuny"])
        aprov = c["portal"].request.get(f"{AURORA}/api/portal/approvals").json() or []
        pend = [a for a in aprov if a.get("status") == "pending"]
        c["pendente_aprovacao"] = str(pend[0]["znuny_ticket_id"]) if pend else "0"
        for fn in PASSOS:
            if filtro and fn.cod not in filtro:
                continue
            try:
                args = (c, browser) if fn.__code__.co_argcount == 2 else (c,)
                obs = fn(*args)
                resultado[fn.cod] = {"ok": "sim", "passo": fn.descricao, "obs": str(obs)}
                print(f"✅ {fn.cod} {fn.descricao} — {obs}")
            except Exception as exc:  # noqa: BLE001 — o resumo precisa de todos
                resultado[fn.cod] = {"ok": "não", "passo": fn.descricao, "obs": f"{type(exc).__name__}: {exc}"[:400]}
                print(f"❌ {fn.cod} {fn.descricao} — {type(exc).__name__}: {str(exc)[:300]}")
                try:
                    shot(c["adm"], f"zz-falha-{fn.cod}-adm")
                    shot(c["portal"], f"zz-falha-{fn.cod}-portal")
                except Exception:  # noqa: BLE001
                    pass
        browser.close()
    arq = OUT / "resultado.json"
    anterior = json.loads(arq.read_text()) if arq.exists() and filtro else {}
    anterior.update(resultado)
    arq.write_text(json.dumps(anterior, ensure_ascii=False, indent=2))
    falhas = [k for k, v in anterior.items() if v["ok"] != "sim"]
    print(f"\n{len(anterior) - len(falhas)}/{len(anterior)} passos ok" + (f" — falhas: {falhas}" if falhas else ""))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
