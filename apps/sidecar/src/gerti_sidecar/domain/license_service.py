"""R16 — licenças, módulos por agente e o "quadrinho" da operação.

*"Hoje tem sete usuários ativos, a gente tem um total de nove. Total de
clientes cadastrados, 60. Contratos ativos, 43. […] Isso aqui impacta no
faturamento da plataforma para a gente."* (09:24)

Três decisões que valem explicação:

**Recusa, não aviso.** Atribuir licença sem seat livre é **erro** (422 com a
contagem na mensagem), não um alerta que dá para clicar por cima. O aceite
A16.2 é explícito, e faz sentido: um aviso ignorável transforma o teto em
sugestão, e o teto é o que a Gerti fatura.

**A contagem é ao vivo, nunca um contador.** `seats_used` é `COUNT(*)` de
licenças ativas, calculado na hora. Um contador incrementado à mão sai do ar
na primeira exceção no meio de uma transação, e a divergência só aparece meses
depois — como um seat fantasma que ninguém consegue liberar.

**Tudo aqui roda na sessão do console** (`AdminSessionLocal`, BYPASSRLS). As
tabelas de licença são `REVOKE ALL ... FROM gerti_app`: a conexão do portal do
cliente nem consegue lê-las. Isso não é redundância — é o aceite A16.6 imposto
pelo banco, para o caso de alguém um dia expor licenciamento numa rota de
cliente por engano.
"""

from __future__ import annotations

import dataclasses
import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.models import AgentLicense, Contract, PlatformLicense, Tenant
from gerti_sidecar.models.enums import ContractStatus
from gerti_sidecar.models.licensing import MODULES


class LicenseError(Exception):
    """Base (-> 422)."""


class NoSeatsAvailable(LicenseError):
    """Não há seat livre para atribuir (-> 422, com a contagem na mensagem)."""


class UnknownModule(LicenseError):
    """Módulo fora do catálogo fechado (-> 422)."""


@dataclasses.dataclass(frozen=True)
class Overview:
    """O "quadrinho" que ele desenhou."""

    seats_total: int
    seats_used: int
    seats_free: int
    tenants_total: int
    contracts_active: int


def validate_modules(modules: list[str]) -> list[str]:
    """Normaliza e recusa módulo fora do catálogo (A16.4).

    A ordem é normalizada e as repetições somem — a comparação de "mudou?" na
    auditoria fica estável, e a tela não depende de mandar na mesma ordem.
    """
    unknown = sorted(set(modules) - set(MODULES))
    if unknown:
        raise UnknownModule(
            f"módulo desconhecido: {', '.join(unknown)} (disponíveis: {', '.join(MODULES)})"
        )
    return [m for m in MODULES if m in set(modules)]


class LicenseService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _license_row(self) -> PlatformLicense:
        row = await self.session.get(PlatformLicense, 1)
        if row is None:  # pragma: no cover - a migration insere a linha
            row = PlatformLicense(id=1, seats_total=0)
            self.session.add(row)
            await self.session.flush()
        return row

    async def seats_used(self) -> int:
        """Licenças ativas AGORA — contagem, nunca contador."""
        return int(
            await self.session.scalar(
                select(func.count()).select_from(AgentLicense).where(AgentLicense.active)
            )
            or 0
        )

    async def overview(self) -> Overview:
        total = (await self._license_row()).seats_total
        used = await self.seats_used()
        tenants = int(
            await self.session.scalar(
                select(func.count()).select_from(Tenant).where(Tenant.archived_at.is_(None))
            )
            or 0
        )
        contracts = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Contract)
                .where(Contract.status == ContractStatus.active)
            )
            or 0
        )
        return Overview(
            seats_total=total,
            seats_used=used,
            seats_free=max(0, total - used),
            tenants_total=tenants,
            contracts_active=contracts,
        )

    async def set_seats_total(self, seats_total: int, *, by: str) -> PlatformLicense:
        """Ajusta o total contratado (D-A: quem define é a Gerti).

        **Reduzir abaixo do que já está em uso é recusado.** A alternativa
        seria revogar licenças sozinho para caber no número novo — tirar acesso
        de gente sem ninguém decidir quem. O operador revoga primeiro, depois
        reduz.
        """
        if seats_total < 0:
            raise LicenseError("o total de licenças não pode ser negativo")
        used = await self.seats_used()
        if seats_total < used:
            raise LicenseError(
                f"há {used} licenças em uso — revogue antes de reduzir o total para {seats_total}"
            )
        row = await self._license_row()
        row.seats_total = seats_total
        row.updated_by = by
        row.updated_at = dt.datetime.now(dt.UTC)
        await self.session.flush()
        return row

    async def get(self, agent_login: str) -> AgentLicense | None:
        return await self.session.get(AgentLicense, agent_login)

    async def list_all(self) -> list[AgentLicense]:
        return list(
            (
                await self.session.execute(
                    select(AgentLicense).order_by(
                        AgentLicense.active.desc(), AgentLicense.agent_login.asc()
                    )
                )
            )
            .scalars()
            .all()
        )

    async def assign(self, agent_login: str, modules: list[str], *, by: str) -> AgentLicense:
        """Atribui (ou atualiza) a licença de um agente.

        Reativar um agente revogado consome um seat como qualquer atribuição
        nova — senão o teto seria burlável revogando e reativando.
        """
        login = agent_login.strip()
        if not login:
            raise LicenseError("informe o login do agente")
        wanted = validate_modules(modules)

        existing = await self.get(login)
        consumes_seat = existing is None or not existing.active
        if consumes_seat:
            overview = await self.overview()
            if overview.seats_free <= 0:
                raise NoSeatsAvailable(
                    f"não há licença disponível: {overview.seats_used} de "
                    f"{overview.seats_total} em uso. Revogue uma licença ou "
                    "aumente o total contratado."
                )

        if existing is None:
            existing = AgentLicense(agent_login=login, assigned_by=by)
            self.session.add(existing)
        existing.active = True
        existing.revoked_at = None
        existing.modules = wanted
        existing.assigned_by = by
        existing.assigned_at = dt.datetime.now(dt.UTC)
        await self.session.flush()
        return existing

    async def revoke(self, agent_login: str) -> AgentLicense | None:
        """Revoga liberando o seat. A linha **fica**, para o histórico."""
        existing = await self.get(agent_login.strip())
        if existing is None or not existing.active:
            return existing
        existing.active = False
        existing.revoked_at = dt.datetime.now(dt.UTC)
        existing.modules = []
        await self.session.flush()
        return existing

    async def modules_of(self, agent_login: str) -> list[str]:
        """Módulos ativos de um agente. Sem licença = nenhum módulo."""
        row = await self.get(agent_login.strip())
        if row is None or not row.active:
            return []
        return list(row.modules or [])
