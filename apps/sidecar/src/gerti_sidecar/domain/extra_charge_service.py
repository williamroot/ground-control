"""Lançamentos avulsos na fatura — T-R15.3, e o conteúdo do contrato livre (T-R15.2).

*"Deslocamento, hora extra, aquele serviço que não estava no contrato."*

Até aqui, tudo que entrava numa fatura vinha do Znuny pelo worker de
reconciliação: horas apontadas em chamado. Não havia como a Gerti lançar um
deslocamento, uma peça, ou um serviço combinado por fora — e é justamente isso
que fecha o R15.

**Não é tabela nova.** Um lançamento avulso é um `consumption_event` como
qualquer outro, com `source_kind` próprio e `recorded_by` = o agente que
lançou. Isso não é economia de esquema, é o que faz o lançamento avulso herdar
de graça tudo o que já existe em volta do consumo: RLS por tenant, glosa
(o cliente pode contestar um deslocamento), fechamento de ciclo, série de
consumo, relatório e fatura. Uma tabela paralela teria de reimplementar as seis
coisas, e a primeira esquecida seria a glosa.

**Dois `source_kind` já são reconhecidos pela fatura** (`invoice_service._KIND_LABELS`):
`travel` ("Deslocamento") e `ticket_work`. Um kind desconhecido não quebra nada
— vira uma linha com o próprio kind como rótulo —, mas fica feio na fatura do
cliente, então a lista abaixo é fechada e a recusa é explícita.

**Por que o lançamento avulso não desconta franquia de hora.** `billable_minutes`
é opcional aqui e o padrão é zero: um deslocamento de R$ 80 não deve comer 0 h
do banco de horas do cliente, nem aparecer como tempo trabalhado no relatório.
Quem quiser lançar hora avulsa informa os minutos de propósito.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.domain.errors import ConsumptionError
from gerti_sidecar.models import ConsumptionEvent, Contract, ServiceCatalogItem
from gerti_sidecar.models.enums import ContractStatus

# Kinds que a fatura sabe rotular. Fechada de propósito — ver o módulo.
ALLOWED_KINDS = ("travel", "ticket_work", "service_item", "expense")

_KIND_LABELS = {
    "travel": "deslocamento",
    "ticket_work": "hora avulsa",
    "service_item": "item de catálogo",
    "expense": "despesa",
}


class ExtraChargeError(ConsumptionError):
    """Lançamento avulso recusado (-> 422)."""


@dataclasses.dataclass(slots=True)
class NewExtraCharge:
    contract_id: uuid.UUID
    kind: str
    description: str
    amount_brl: float
    recorded_by: str
    occurred_on: dt.date | None = None
    quantity: float = 1.0
    minutes: float = 0.0
    service_id: uuid.UUID | None = None


class ExtraChargeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, data: NewExtraCharge) -> ConsumptionEvent:
        if data.kind not in ALLOWED_KINDS:
            raise ExtraChargeError(
                f"tipo de lançamento desconhecido: {data.kind!r} "
                f"(use um de {', '.join(ALLOWED_KINDS)})"
            )
        description = data.description.strip()
        if not description:
            raise ExtraChargeError("descreva o lançamento — ele vai aparecer na fatura do cliente")
        if data.quantity <= 0:
            raise ExtraChargeError("quantidade deve ser maior que zero")
        if data.amount_brl < 0:
            raise ExtraChargeError("valor não pode ser negativo")
        if data.minutes < 0:
            raise ExtraChargeError("minutos não podem ser negativos")

        # RLS já escopa o contrato ao tenant da sessão; `get` devolvendo None
        # significa "não é seu" tanto quanto "não existe", e a resposta é a
        # mesma nos dois casos de propósito.
        contract = await self.session.get(Contract, data.contract_id)
        if contract is None:
            raise ExtraChargeError("contrato inexistente neste tenant")
        if contract.status in (ContractStatus.terminated, ContractStatus.expired):
            # Suspenso ainda aceita: serviço parado pode ter deslocamento
            # pendente de lançar. Encerrado, não — lançar em contrato morto
            # gera cobrança que ninguém consegue explicar depois.
            raise ExtraChargeError(
                f"contrato {contract.code} está {contract.status} — " "não aceita lançamento novo"
            )

        if data.service_id is not None:
            item = await self.session.get(ServiceCatalogItem, data.service_id)
            if item is None:
                raise ExtraChargeError("item de catálogo inexistente neste tenant")

        occurred_on = data.occurred_on or dt.datetime.now(dt.UTC).date()
        if occurred_on < contract.starts_on:
            raise ExtraChargeError(
                f"a data do lançamento ({occurred_on}) é anterior ao início do contrato "
                f"({contract.starts_on})"
            )

        total = round(float(data.amount_brl) * float(data.quantity), 2)
        # `source_ref` precisa ser único por lançamento para o histórico ficar
        # rastreável; sem webhook_event_id, a idempotência aqui é do operador.
        ref = f"manual:{uuid.uuid4()}"
        return await ConsumptionService(self.session).record(
            RecordConsumption(
                contract_id=data.contract_id,
                occurred_at=dt.datetime.combine(occurred_on, dt.time(12), tzinfo=dt.UTC),
                source_kind=data.kind,
                source_ref=ref,
                billable_minutes=float(data.minutes) * float(data.quantity),
                billable_amount_brl=total,
                recorded_by=data.recorded_by,
                service_id=data.service_id,
            )
        )
