"""Materializa tarefas recorrentes vencidas em chamados (T-R11.3, R11).

*"É uma agenda. Isso é importante também, porque é o dia a dia dos técnicos."*
(07:09)

## A garantia que este módulo existe para dar

Rodar duas vezes no mesmo dia gera **um** chamado, não dois. E ela não vem de
um `if` bem colocado: vem do `UNIQUE(task_id, occurrence_date)` da tabela
`recurring_task_run`. O serviço **grava a marca de ocorrência primeiro** e só
então abre o chamado no Znuny. Se dois processos correrem juntos, o segundo
bate no índice único e desiste — o Postgres decide, não a ordem de execução.

O preço dessa escolha é honesto e está declarado: se a marca gravar e a criação
do chamado falhar, aquela ocorrência fica registrada com `error` preenchido e
**não é tentada de novo automaticamente**. Preferimos a falha visível (uma
linha com erro, que a tela mostra) ao risco de abrir o mesmo chamado duas vezes
para o técnico. Reprocessar é apagar a linha de erro — ato deliberado.

## O que este módulo NÃO faz

Não debita contrato por conta própria. `contract_id` vazio significa "não
consome" (suposição S4) — e mesmo preenchido, quem debita é o worker de
consumo, ao reconciliar as horas que o técnico lançar no chamado.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.recurrence import next_occurrence
from gerti_sidecar.models import RecurringTask, RecurringTaskRun, TicketContractLink

logger = logging.getLogger(__name__)

# Quanto tempo para trás o processador recupera ocorrências perdidas. Uma
# semana cobre o worker fora do ar por um ou dois dias — o caso real — sem
# abrir chamado retroativo de um mês que já passou. Ver `due_tasks`.
DEFAULT_CATCH_UP_DAYS = 7


@dataclass(slots=True)
class MaterializeResult:
    created: int = 0
    skipped: int = 0
    failed: int = 0
    ticket_ids: list[int] | None = None


class RecurringTaskService:
    """Sessão RLS-scoped no tenant. `gi` é o cliente de tickets do Znuny."""

    def __init__(self, session: AsyncSession, gi: Any) -> None:
        self.session = session
        self._gi = gi

    async def due_tasks(
        self, *, today: dt.date, catch_up_days: int = DEFAULT_CATCH_UP_DAYS
    ) -> list[tuple[RecurringTask, dt.date]]:
        """Ocorrências vencidas **dentro da janela de recuperação**.

        A janela existe por um erro que o teste pegou antes do deploy: a
        primeira versão caminhava desde `starts_on`, então uma tarefa
        cadastrada em janeiro e processada em agosto abriria, um por vez, todos
        os chamados retroativos. Ninguém quer chegar na segunda-feira com trinta
        "verificação de backup" atrasadas de meses que já passaram.

        A regra que ficou tem duas partes:

        1. **Janela de recuperação** (`catch_up_days`, padrão uma semana):
           ocorrência mais velha que isso é ignorada. Aquele momento passou;
           abrir o chamado agora não recupera o trabalho, só polui a agenda.
        2. **No máximo UMA ocorrência por tarefa em cada execução** — a mais
           recente que ainda não virou chamado. Se três verificações de backup
           venceram, o técnico precisa de *um* chamado dizendo "verifique o
           backup", não de três idênticos. O trabalho é o mesmo.
        """
        tasks = (
            (
                await self.session.execute(
                    select(RecurringTask)
                    .where(RecurringTask.active.is_(True))
                    .order_by(RecurringTask.title)
                )
            )
            .scalars()
            .all()
        )
        floor = today - dt.timedelta(days=max(0, catch_up_days))
        due: list[tuple[RecurringTask, dt.date]] = []
        for t in tasks:
            # A ÚLTIMA ocorrência que já venceu, dentro da janela.
            latest: dt.date | None = None
            occurrence = next_occurrence(
                frequency=t.frequency,
                starts_on=t.starts_on,
                ends_on=t.ends_on,
                weekday=t.weekday,
                day_of_month=t.day_of_month,
                after=max(floor, t.starts_on),
            )
            while occurrence is not None and occurrence <= today:
                latest = occurrence
                occurrence = next_occurrence(
                    frequency=t.frequency,
                    starts_on=t.starts_on,
                    ends_on=t.ends_on,
                    weekday=t.weekday,
                    day_of_month=t.day_of_month,
                    after=occurrence + dt.timedelta(days=1),
                )
            if latest is None:
                continue
            # Já materializamos essa ou uma POSTERIOR? Então não há nada a
            # fazer. Comparar por `>=`, e não por igualdade, é o que faz o
            # processador convergir: as ocorrências antigas da janela ficam
            # cobertas pela mais recente e não voltam a ser consideradas a cada
            # execução — que foi exatamente o laço que o teste pegou.
            covered = await self.session.scalar(
                select(RecurringTaskRun.id).where(
                    RecurringTaskRun.task_id == t.id,
                    RecurringTaskRun.occurrence_date >= latest,
                )
            )
            if covered is None:
                due.append((t, latest))
        return due

    async def materialize(
        self,
        *,
        tenant_id: uuid.UUID,
        customer_id: str,
        today: dt.date,
        catch_up_days: int = DEFAULT_CATCH_UP_DAYS,
    ) -> MaterializeResult:
        result = MaterializeResult(ticket_ids=[])
        for task, occurrence in await self.due_tasks(today=today, catch_up_days=catch_up_days):
            # 1) A MARCA PRIMEIRO. É o índice único que decide quem ganha a
            #    corrida; sem isso, dois ticks simultâneos abrem dois chamados.
            run = RecurringTaskRun(tenant_id=tenant_id, task_id=task.id, occurrence_date=occurrence)
            self.session.add(run)
            try:
                await self.session.flush()
            except IntegrityError:
                # Outro processo chegou antes. Não é erro — é a garantia
                # funcionando.
                await self.session.rollback()
                result.skipped += 1
                continue

            # 2) Só então o chamado.
            try:
                created = await self._gi.create_ticket(
                    customer_user=task.customer_user_login,
                    customer_id=customer_id,
                    title=task.title,
                    body=task.body or task.title,
                    service=task.service,
                    type_=task.type,
                    priority=task.priority,
                    contract_id=str(task.contract_id) if task.contract_id else "",
                    queue=task.znuny_queue_name,
                )
            except Exception as exc:  # falha visível, nunca silenciosa
                logger.warning(
                    "tarefa recorrente %s (%s) falhou ao virar chamado: %s",
                    task.id,
                    occurrence,
                    exc,
                )
                run.error = str(exc)[:500]
                await self.session.flush()
                result.failed += 1
                continue

            run.znuny_ticket_id = created.znuny_ticket_id
            # Vincula ao contrato SÓ se a tarefa tiver um. Vazio = preventiva
            # que não consome (suposição S4).
            if task.contract_id:
                self.session.add(
                    TicketContractLink(
                        znuny_ticket_id=created.znuny_ticket_id,
                        contract_id=task.contract_id,
                        tenant_id=tenant_id,
                        linked_by_rule=f"recurring:{task.id}",
                    )
                )
            await self.session.flush()
            result.created += 1
            assert result.ticket_ids is not None
            result.ticket_ids.append(created.znuny_ticket_id)
        return result
