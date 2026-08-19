"""Licenciamento e módulos por agente (R16, Onda 6).

**Dado da operação, não do cliente.** Nenhuma destas tabelas tem `tenant_id` e
nenhuma tem RLS: elas não pertencem a cliente nenhum. A proteção é outra e é
mais forte — `REVOKE ALL ... FROM gerti_app` na migration 0033. A conexão que
atende o portal do cliente **não enxerga** licenciamento, e é assim que o
aceite A16.5/A16.6 vira garantia de banco em vez de disciplina de código.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import ARRAY, Boolean, DateTime, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base

# Catálogo FECHADO. Só o que o produto tem hoje — WhatsApp e acesso remoto
# ficam de fora até o recurso existir, para não vender botão que não faz nada.
# O mesmo par está no CHECK da tabela: módulo inventado é recusado pelo banco.
MODULES = ("tickets", "inventory")

MODULE_LABELS = {
    "tickets": "Chamados",
    "inventory": "Inventário",
}


class PlatformLicense(Base):
    """Linha ÚNICA (CHECK `id = 1`) com o total de seats contratado.

    Duas linhas dariam duas respostas para "quantos seats temos?", e a leitura
    passaria a depender da ordem do SELECT.
    """

    __tablename__ = "platform_license"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seats_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(Text)


class AgentLicense(Base):
    """Licença de um agente e os módulos que ela habilita.

    A chave é o **login no Znuny**, que é o dono da identidade (D-C): não
    duplicamos o agente aqui, guardamos só o que é nosso.
    """

    __tablename__ = "agent_license"

    agent_login: Mapped[str] = mapped_column(Text, primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    modules: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("ARRAY[]::text[]")
    )
    assigned_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    assigned_by: Mapped[str | None] = mapped_column(Text)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
