"""R13b — checklists personalizáveis (a lacuna da Onda 4).

*"Temos aqui configurações de feriados, checklists personalizáveis."* — 08:16

Duas metades com donos diferentes, e isso decide o esquema:

- **Modelo** (`checklist_template`) é procedimento da GERTI: "onboarding de
  estação", "troca de servidor". Não pertence a cliente nenhum — não tem
  `tenant_id`, não tem RLS.
- **Instância** (`ticket_checklist`) é o modelo aplicado a UM chamado, e o
  chamado é de um cliente. Tem `tenant_id`, RLS e `UNIQUE(znuny_ticket_id,
  template_id)` — aplicar o mesmo modelo duas vezes não duplica a lista
  (aceite A13.5).

**Os itens da instância são copiados, não referenciados.** Editar o modelo
depois **não** pode mudar um checklist que já foi executado: o registro do que
o técnico marcou tem de continuar sendo o que ele viu na hora. É o mesmo
princípio do `unit_price_at_event` na cobrança.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0034_checklists"
down_revision: str | None = "0033_licenciamento"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enable_tenant_rls(table: str) -> None:
    op.execute(f"ALTER TABLE gerti.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE gerti.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_isolation ON gerti.{table} "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.{table} TO gerti_app")


def upgrade() -> None:
    # ── modelo (procedimento da Gerti, global) ─────────────────────────────
    op.create_table(
        "checklist_template",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", sa.Text()),
        sa.UniqueConstraint("name", name="uq_checklist_template_name"),
        schema="gerti",
    )
    op.create_table(
        "checklist_template_item",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "template_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.checklist_template.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False),
        schema="gerti",
    )
    op.execute(
        "CREATE INDEX ix_checklist_template_item_order ON gerti.checklist_template_item "
        "(template_id, position)"
    )

    # ── instância (o modelo aplicado a um chamado) ─────────────────────────
    op.create_table(
        "ticket_checklist",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.tenant.id"),
            nullable=False,
        ),
        sa.Column("znuny_ticket_id", sa.BigInteger(), nullable=False),
        # SEM ondelete=CASCADE de propósito: apagar um modelo não pode sumir
        # com o registro do que foi executado num chamado.
        sa.Column(
            "template_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.checklist_template.id"),
            nullable=False,
        ),
        # Nome copiado na aplicação: o modelo pode ser renomeado depois.
        sa.Column("template_name", sa.Text(), nullable=False),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("applied_by", sa.Text(), nullable=False),
        # A13.5 — aplicar duas vezes não duplica.
        #
        # `tenant_id` faz PARTE da chave, como em `ticket_approval`. Sem ele, o
        # modelo Onda-6 quebra em instalação com mais de uma instância Znuny,
        # onde o id de chamado se repete entre clientes: o segundo cliente a
        # aplicar o mesmo modelo no mesmo número de chamado colidiria com o
        # primeiro. Um teste de isolamento pegou isso.
        sa.UniqueConstraint(
            "tenant_id",
            "znuny_ticket_id",
            "template_id",
            name="uq_ticket_checklist_tenant_ticket_template",
        ),
        schema="gerti",
    )
    op.create_table(
        "ticket_checklist_item",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "checklist_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.ticket_checklist.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Denormalizado para a policy RLS não precisar de subselect.
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.tenant.id"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        # Texto COPIADO do modelo: editar o modelo depois não muda o que o
        # técnico viu quando marcou.
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("done_at", sa.DateTime(timezone=True)),
        sa.Column("done_by", sa.Text()),
        schema="gerti",
    )
    op.execute(
        "CREATE INDEX ix_ticket_checklist_item_order ON gerti.ticket_checklist_item "
        "(checklist_id, position)"
    )
    op.execute(
        "CREATE INDEX ix_ticket_checklist_ticket ON gerti.ticket_checklist "
        "(tenant_id, znuny_ticket_id)"
    )

    for table in ("ticket_checklist", "ticket_checklist_item"):
        _enable_tenant_rls(table)

    # O modelo é LIDO durante a aplicação, que roda na sessão do cliente
    # (RLS-subject) porque a instância é escopada por tenant. Só SELECT: criar
    # e desativar modelo é do console, que usa o papel do administrador.
    # Modelo não guarda dado de cliente nenhum — é procedimento da Gerti.
    for table in ("checklist_template", "checklist_template_item"):
        op.execute(f"GRANT SELECT ON gerti.{table} TO gerti_app")


def downgrade() -> None:
    for table in ("ticket_checklist_item", "ticket_checklist"):
        op.execute(f"REVOKE ALL ON gerti.{table} FROM gerti_app")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON gerti.{table}")
        op.execute(f"ALTER TABLE gerti.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE gerti.{table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table, schema="gerti")
    for table in ("checklist_template", "checklist_template_item"):
        op.execute(f"REVOKE ALL ON gerti.{table} FROM gerti_app")
    op.drop_table("checklist_template_item", schema="gerti")
    op.drop_table("checklist_template", schema="gerti")
