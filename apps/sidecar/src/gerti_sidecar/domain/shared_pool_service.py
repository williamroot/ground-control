"""T-R3.2 — bolsa de crédito compartilhada entre contratos do mesmo cliente.

*"A matriz compra o crédito e as filiais consomem daquele bolo."*

`gerti.shared_credit_pool` e `contract.shared_pool_id` existem desde a Spec #0
e **nada no sistema jamais os leu**: um contrato `credit_shared` gastava o
próprio `initial_amount_brl`, exatamente como um `credit_brl`. Ou seja, o tipo
existia no menu e não compartilhava nada — cada filial tinha a sua bolsa
inteira, e a soma do que o cliente podia gastar era o número de filiais vezes
o crédito comprado uma vez só.

**O saldo é do grupo, não do contrato.** É essa a inversão desta tarefa: para
um contrato ligado a uma bolsa, `remaining = total da bolsa - consumo de TODOS
os contratos ligados a ela`. Duas filiais consultando ao mesmo tempo veem o
mesmo número, que é o ponto do recurso.

**O que continua fora de escopo, e por quê.** A bolsa tem ciclo próprio
(`cycle_kind`, `cycle_period_months`, `current_cycle_start`) e nada aqui o
avança: o saldo é acumulado desde o início da bolsa. Renovar a bolsa por ciclo
é decisão de dinheiro que ninguém tomou ainda — se a bolsa fosse renovada
automaticamente, um cliente que gastou tudo em maio veria crédito novo em
junho sem ter comprado. Deixar acumulado erra para o lado de cobrar a mais e
ser percebido, não para o de liberar crédito que não existe.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.contract_read_service import not_written_off_predicate
from gerti_sidecar.domain.errors import ContractValidationError
from gerti_sidecar.models import ConsumptionEvent, Contract, SharedCreditPool
from gerti_sidecar.models.enums import ContractType, CycleKind


class SharedPoolError(ContractValidationError):
    """Operação inválida sobre a bolsa (-> 422)."""


@dataclasses.dataclass(slots=True)
class NewSharedPool:
    name: str
    total_amount_brl: float
    cycle_kind: CycleKind = CycleKind.billing
    cycle_period_months: int = 1
    current_cycle_start: dt.date | None = None


@dataclasses.dataclass(slots=True)
class PoolBalance:
    pool_id: uuid.UUID
    name: str
    total_brl: float
    consumed_brl: float
    remaining_brl: float
    contract_ids: list[uuid.UUID]


class SharedPoolService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _tenant_id(self) -> uuid.UUID:
        """Tenant da sessão — o GUC que a RLS já usa, sem confiar em parâmetro."""
        value = await self.session.scalar(select(func.current_setting("app.current_tenant", True)))
        if not value:
            raise SharedPoolError("sessão sem tenant")
        return uuid.UUID(str(value))

    async def create(self, data: NewSharedPool) -> SharedCreditPool:
        if data.total_amount_brl <= 0:
            raise SharedPoolError("o valor da bolsa deve ser maior que zero")
        if data.cycle_period_months < 1:
            raise SharedPoolError("o período da bolsa deve ser de pelo menos 1 mês")
        pool = SharedCreditPool(
            tenant_id=await self._tenant_id(),
            name=data.name.strip() or "Bolsa compartilhada",
            total_amount_brl=data.total_amount_brl,
            cycle_kind=data.cycle_kind,
            cycle_period_months=data.cycle_period_months,
            current_cycle_start=data.current_cycle_start or dt.datetime.now(dt.UTC).date(),
        )
        self.session.add(pool)
        await self.session.flush()
        return pool

    # NÃO chamar este método de `list`: dentro do corpo da classe o nome
    # sombrearia o builtin `list` nas anotações dos outros métodos.
    async def all_pools(self) -> list[SharedCreditPool]:
        # RLS escopa ao tenant da sessão.
        return list(
            (await self.session.execute(select(SharedCreditPool).order_by(SharedCreditPool.name)))
            .scalars()
            .all()
        )

    async def link(self, pool_id: uuid.UUID, contract_id: uuid.UUID) -> Contract:
        """Liga um contrato à bolsa.

        Só `credit_shared` pode ser ligado. Deixar um banco de horas apontar
        para uma bolsa em reais criaria um contrato com duas fontes de saldo em
        unidades diferentes, e a pergunta "quanto sobra?" deixaria de ter uma
        resposta.
        """
        pool = await self.session.get(SharedCreditPool, pool_id)
        if pool is None:
            raise SharedPoolError("bolsa inexistente neste tenant")
        contract = await self.session.get(Contract, contract_id)
        if contract is None:
            raise SharedPoolError("contrato inexistente neste tenant")
        if contract.type != ContractType.credit_shared:
            raise SharedPoolError(
                f"apenas contratos do tipo crédito compartilhado entram numa bolsa "
                f"(o contrato {contract.code} é {contract.type})"
            )
        contract.shared_pool_id = pool.id
        await self.session.flush()
        return contract

    async def unlink(self, contract_id: uuid.UUID) -> Contract:
        contract = await self.session.get(Contract, contract_id)
        if contract is None:
            raise SharedPoolError("contrato inexistente neste tenant")
        contract.shared_pool_id = None
        await self.session.flush()
        return contract

    async def contracts_in(self, pool_id: uuid.UUID) -> list[Contract]:
        return list(
            (
                await self.session.execute(
                    select(Contract)
                    .where(Contract.shared_pool_id == pool_id)
                    .order_by(Contract.code.asc())
                )
            )
            .scalars()
            .all()
        )

    async def balance(self, pool_id: uuid.UUID) -> PoolBalance:
        pool = await self.session.get(SharedCreditPool, pool_id)
        if pool is None:
            raise SharedPoolError("bolsa inexistente neste tenant")
        contracts = await self.contracts_in(pool_id)
        ids = [c.id for c in contracts]
        consumed = 0.0
        if ids:
            consumed = float(
                await self.session.scalar(
                    select(func.coalesce(func.sum(ConsumptionEvent.billable_amount_brl), 0)).where(
                        ConsumptionEvent.contract_id.in_(ids),
                        # Mesma regra de glosa do resto do financeiro — nunca
                        # reescrita aqui (o `NULL NOT IN (..)` é armadilha).
                        not_written_off_predicate(),
                    )
                )
                or 0
            )
        total = float(pool.total_amount_brl)
        return PoolBalance(
            pool_id=pool.id,
            name=pool.name,
            total_brl=total,
            consumed_brl=round(consumed, 2),
            remaining_brl=round(total - consumed, 2),
            contract_ids=ids,
        )
