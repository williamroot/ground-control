"""recurring_task — a agenda de atividades que viram chamado (T-R11.1, R11)

Revision ID: 0031_recurring_task
Revises: 0030_consumption_orphan
Create Date: 2026-08-19

*"Verificação de backup, verificação de patches, vulnerabilidades, atualização
de servidor… que acontecem uma vez, que acontecem toda semana, que acontecem
todo mês. É uma agenda. Isso é importante também, porque é o dia a dia dos
técnicos."* — 07:09

Ele não enquadra isso como automação de bastidor: é a **agenda de trabalho da
equipe**. Por isso a tarefa recorrente é entidade de primeira classe, com tela
própria, e não uma regra escondida no motor de automação.

**Duas tabelas, e a segunda é a que importa.** `recurring_task` é o cadastro;
`recurring_task_run` é o registro de cada ocorrência **materializada**, com
`UNIQUE(task_id, occurrence_date)`. Sem ela, um worker que reinicia — ou dois
ticks no mesmo dia — abriria o mesmo chamado duas vezes, e o técnico acordaria
com a agenda duplicada. A idempotência é do banco, não do código.

**`contract_id` é NULLABLE de propósito (suposição S4).** Não sabemos se
manutenção preventiva consome o contrato do cliente: em MSP às vezes é cortesia
contratual, às vezes é trabalho faturável, e o Kleber não disse. Vazio = **não
consome**, que é a leitura conservadora; quem quiser vincular, vincula. As duas
leituras cabem sem refazer o modelo.

FORCE RLS por tenant_id — template canônico das irmãs (0011/0012/0029).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0031_recurring_task"
down_revision: str | None = "0030_consumption_orphan"
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
    op.create_table(
        "recurring_task",
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
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=sa.text("''")),
        # As três recorrências que ele nomeia em 07:09, e só elas. Uma quarta
        # ("a cada N dias") seria invenção nossa.
        sa.Column("frequency", sa.Text(), nullable=False),
        # weekly: 0=segunda … 6=domingo (ISO). monthly: dia do mês.
        sa.Column("weekday", sa.SmallInteger()),
        sa.Column("day_of_month", sa.SmallInteger()),
        sa.Column("at_time", sa.Time(), nullable=False, server_default=sa.text("'08:00'")),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date()),
        # Onde o chamado nasce e como ele se parece.
        sa.Column("znuny_queue_name", sa.Text()),
        sa.Column("service", sa.Text()),
        sa.Column("type", sa.Text()),
        sa.Column("priority", sa.Text()),
        sa.Column("customer_user_login", sa.Text(), nullable=False),
        # S4: vazio = não consome contrato. Ver o cabeçalho deste arquivo.
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.contract.id", ondelete="SET NULL"),
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.Text(), nullable=False),
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
        sa.CheckConstraint(
            "frequency IN ('once','weekly','monthly')", name="ck_recurring_task_frequency"
        ),
        sa.CheckConstraint(
            "weekday IS NULL OR (weekday BETWEEN 0 AND 6)", name="ck_recurring_task_weekday"
        ),
        sa.CheckConstraint(
            "day_of_month IS NULL OR (day_of_month BETWEEN 1 AND 31)",
            name="ck_recurring_task_day_of_month",
        ),
        # A forma precisa bater com a frequência. Uma tarefa semanal sem dia da
        # semana não tem próxima ocorrência calculável — e o banco recusa antes
        # de ela existir, em vez de o worker descobrir isso todo dia.
        sa.CheckConstraint(
            "(frequency <> 'weekly' OR weekday IS NOT NULL) AND "
            "(frequency <> 'monthly' OR day_of_month IS NOT NULL)",
            name="ck_recurring_task_shape",
        ),
        schema="gerti",
    )
    _enable_tenant_rls("recurring_task")

    op.create_table(
        "recurring_task_run",
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
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.recurring_task.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("znuny_ticket_id", sa.Integer()),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # A garantia que impede a agenda duplicada. Ver o cabeçalho.
        sa.UniqueConstraint("task_id", "occurrence_date", name="uq_recurring_task_run_occurrence"),
        schema="gerti",
    )
    _enable_tenant_rls("recurring_task_run")


def downgrade() -> None:
    for table in ("recurring_task_run", "recurring_task"):
        op.execute(f"REVOKE ALL ON gerti.{table} FROM gerti_app")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON gerti.{table}")
        op.execute(f"ALTER TABLE gerti.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE gerti.{table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table, schema="gerti")
