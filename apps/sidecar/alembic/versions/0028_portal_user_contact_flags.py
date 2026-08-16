"""portal_user_role: chave "libera chamados por e-mail" (T-R2.1, Onda 1 — R2)

Revision ID: 0028_portal_user_contact_flags
Revises: 0027_tenant_address_contact
Create Date: 2026-08-15

O Kleber pede a chave *"libera tickets por e-mail"* por pessoa (01:44). A
identidade do usuário mora no Znuny (decisão D-C: Znuny dono da identidade;
`gerti` guarda papel e flags) — então a flag é **nossa**, ao lado do papel, e
não um campo do `customer_user`.

`DEFAULT true`: o cadastro único é o diferencial que o vídeo pede (a mesma
pessoa abre chamado pelo portal e por e-mail). Nascer desligado inverteria a
promessa para todo mundo que já está cadastrado.

NOT NULL com default preenche as linhas existentes na própria migration —
`portal_user_role` é tabela pequena (papéis, não eventos), então o rewrite é
barato e não exige janela.

`extension` (o **ramal** de 02:27) também mora aqui, e isso merece justificativa
porque parece contrariar D-C: o mapa nativo do `customer_user` tem `phone`,
`mobile`, `street`, `city` — e **não tem ramal**. Colocá-lo no Znuny exigiria
coluna nova no núcleo, que a invariante 4 proíbe; enfiá-lo num campo livre
(`comments`, `fax`) seria pior. Então: telefone e celular vão para o Znuny, que
é o dono da identidade; o ramal fica do nosso lado, com a limitação declarada —
ele não aparece no painel nativo.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028_portal_user_contact_flags"
down_revision: str | None = "0027_tenant_address_contact"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "portal_user_role",
        sa.Column(
            "email_intake_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        schema="gerti",
    )
    op.add_column(
        "portal_user_role",
        sa.Column("extension", sa.Text(), nullable=True),
        schema="gerti",
    )


def downgrade() -> None:
    op.drop_column("portal_user_role", "extension", schema="gerti")
    op.drop_column("portal_user_role", "email_intake_enabled", schema="gerti")
