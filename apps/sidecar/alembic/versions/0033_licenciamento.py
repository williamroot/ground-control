"""Onda 6 — licenciamento e módulos por agente (R16).

*"Hoje tem sete usuários ativos, a gente tem um total de nove. […] Isso aqui
impacta no faturamento da plataforma para a gente."* (09:24)

Três coisas que definem o desenho:

1. **Dado da OPERAÇÃO, não do cliente.** Licença é assunto da Gerti com ela
   mesma; nenhum cliente pode ver quantos seats existem nem quem tem qual
   módulo. Por isso as duas tabelas **não** têm `tenant_id`, **não** têm RLS —
   e são `REVOKE ALL ... FROM gerti_app`. A conexão da aplicação (a que atende
   o portal do cliente) simplesmente **não enxerga** estas tabelas; só o papel
   do console (`gerti_admin_user`, BYPASSRLS) lê. É o aceite A16.6, imposto no
   banco em vez de confiado ao código.

2. **O total contratado é da Gerti** (decisão D-A). `seats_total` é campo
   editável no console com auditoria, não valor herdado de contrato externo.
   Por isso ele mora numa tabela de linha única (`platform_license`), com
   CHECK garantindo que só existe uma.

3. **Só os módulos que existem no produto hoje.** `tickets` e `inventory`, e
   mais nada — WhatsApp e acesso remoto ficam de fora até haver o recurso.
   Vender botão que não faz nada é pior do que não ter o botão.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0033_licenciamento"
down_revision: str | None = "0032_onda5_financeiro"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_license",
        # Linha única: o CHECK abaixo impede a segunda. Sem isso, duas linhas
        # dariam duas respostas para "quantos seats temos?", e a leitura
        # dependeria da ordem do SELECT.
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seats_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_by", sa.Text()),
        sa.CheckConstraint("id = 1", name="ck_platform_license_singleton"),
        sa.CheckConstraint("seats_total >= 0", name="ck_platform_license_seats_non_negative"),
        schema="gerti",
    )
    op.execute("INSERT INTO gerti.platform_license (id, seats_total) VALUES (1, 0)")

    op.create_table(
        "agent_license",
        # A chave é o login do agente no Znuny — que é o dono da identidade
        # (D-C). Não duplicamos o agente aqui; guardamos só o que é nosso.
        sa.Column("agent_login", sa.Text(), primary_key=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        # Módulos como array de texto, com o catálogo fechado imposto pelo
        # CHECK: módulo inventado é recusado pelo BANCO (aceite A16.4), não só
        # pela validação da aplicação.
        sa.Column(
            "modules",
            sa.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("assigned_by", sa.Text()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "modules <@ ARRAY['tickets','inventory']::text[]",
            name="ck_agent_license_modules",
        ),
        schema="gerti",
    )
    op.execute(
        "CREATE INDEX ix_agent_license_active ON gerti.agent_license (agent_login) " "WHERE active"
    )

    # A16.6 — a conexão da aplicação não enxerga licenciamento. Vale para as
    # duas tabelas: `platform_license` também expõe o tamanho do contrato da
    # Gerti, que é dado comercial dela.
    for table in ("platform_license", "agent_license"):
        op.execute(f"REVOKE ALL ON gerti.{table} FROM gerti_app")


def downgrade() -> None:
    op.drop_index("ix_agent_license_active", table_name="agent_license", schema="gerti")
    op.drop_table("agent_license", schema="gerti")
    op.drop_table("platform_license", schema="gerti")
