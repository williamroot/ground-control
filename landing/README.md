# Ground Control — Landing

Landing page comercial do **Ground Control**: plataforma de Service Desk own-source, white-label, MSP-first. Estética *mission-control / aeroespacial*. Engineered by **WAS Soluções em Tecnologia**.

> Repo separado da infra `ground-control` (que é a stack Znuny). Pode ser movida para `apps/landing/` no monorepo de deploy quando a infra estabilizar.

## Stack

Site 100% estático: `index.html` + `css/style.css` + `js/main.js` + `assets/`. Sem build step.

- Tipografia: Saira Condensed (display) · Saira (head) · Archivo (body) · JetBrains Mono (telemetria)
- Acento: ignition amber `#FF6B1A`; status GO `#36D399`; fundo deep-space `#070A12`
- Interações: relógio UTC de missão, count-up de telemetria, reveal on scroll, form de demo com fallback mailto (sem backend ainda — ver abaixo)

## Rodar local

```bash
python3 -m http.server 8000   # http://localhost:8000
```

## Deploy (VPS + Cloudflare Tunnel) — domínio groundcontrol.was.dev.br

```bash
cp .env.prod.example .env.prod
# colar o token do tunnel "groundcontrol" (Zero Trust → Networks → Tunnels)
docker compose -f docker-compose-prod.yml --env-file .env.prod up -d
docker compose -f docker-compose-prod.yml logs -f cloudflared
```

No dashboard Cloudflare, Public Hostname do tunnel `groundcontrol`:
`groundcontrol.was.dev.br` → Type `HTTP` → URL `web:80`.

## Formulário de demonstração

O form em `#demo` valida client-side e, **sem backend conectado**, abre o cliente de e-mail
pré-preenchido para `contato@was.dev.br` (fallback gracioso). Para captar leads de verdade,
trocar o handler em `js/main.js` por um POST para Formspree / endpoint próprio / CRM.
Esse ponto está marcado e isolado na função de submit.

## Próximos passos sugeridos

- Conectar o form a um endpoint real de leads
- Adicionar OG image dedicada em `assets/`
- A/B no headline e no CTA primário
