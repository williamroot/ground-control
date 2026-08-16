"""tenant_queue — quais filas cada cliente acessa, e qual é a padrão (T-R5.1, R5)

Revision ID: 0029_tenant_queue
Revises: 0028_portal_user_contact_flags
Create Date: 2026-08-15

R5 do vídeo (04:03): *"aqui a gente vai falar quais filas de atendimento o cara
vai ter acesso… a gente tem uma fila padrão"*. Hoje isso não existe em nenhuma
tabela, e a fila padrão é a string `'Raw'` fixa em `TicketCreate.pm:67` — todo
chamado de todo cliente cai no mesmo lugar.

**Por que uma tabela nova não viola D21 (zero persistência de configuração do
Znuny):** a associação cliente↔fila **não existe** no Znuny. O Znuny sabe quais
filas existem e a que grupo pertencem; ele não tem o conceito "esta empresa
acessa estas filas". Isto é dado nosso, não cópia. `znuny_queue_name` é
denormalização declarada — serve para exibir a lista sem uma ida ao GI a cada
render; a **verdade** do nome continua sendo o Znuny, e a gravação valida o id
contra a lista viva antes de persistir (T-R5.2).

Decisão D-F (fechada 15/08), com a limitação registrada: a restrição vale na
**nossa** camada (portal e API). Um agente logado na interface nativa do Znuny
não a enxerga.

FORCE RLS por tenant_id — template canônico das irmãs (0011/0012).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0029_tenant_queue"
down_revision: str | None = "0028_portal_user_contact_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_queue",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("znuny_queue_id", sa.Integer(), nullable=False),
        sa.Column("znuny_queue_name", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "znuny_queue_id", name="uq_tenant_queue_tenant_queue"),
        schema="gerti",
    )
    # No MÁXIMO uma fila padrão por cliente — garantido no banco, não na
    # aplicação (molde: ux_agent_timer_active, migration 0014). Sem isto, duas
    # gravações concorrentes deixariam o cliente com dois "padrões" e a abertura
    # de chamado escolheria um deles de forma não-determinística.
    op.execute(
        "CREATE UNIQUE INDEX ux_tenant_queue_default ON gerti.tenant_queue "
        "(tenant_id) WHERE is_default"
    )
    op.execute("ALTER TABLE gerti.tenant_queue ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.tenant_queue FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_queue_tenant_isolation ON gerti.tenant_queue "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.tenant_queue TO gerti_app")


def downgrade() -> None:
    op.execute("REVOKE ALL ON gerti.tenant_queue FROM gerti_app")
    op.execute("DROP POLICY IF EXISTS tenant_queue_tenant_isolation ON gerti.tenant_queue")
    op.execute("ALTER TABLE gerti.tenant_queue NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.tenant_queue DISABLE ROW LEVEL SECURITY")
    op.drop_table("tenant_queue", schema="gerti")
