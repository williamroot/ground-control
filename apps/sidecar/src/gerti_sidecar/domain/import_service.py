"""Importação em lote de clientes e usuários por CSV (T-R8.1/8.2/8.3, R8).

*"Tem as importações que a gente pode eventualmente fazer. Quero importar
cadastros, quero importar cliente, quero importar usuário do cliente."* (12:40)

O contexto que dá o tamanho disso: a migração do TIFLUX são **60 clientes e 43
contratos ativos**. Sem carga em lote, isso é feito um a um, à mão, pelo
assistente de cadastro.

## Três decisões que este módulo materializa

**1. Simular antes de gravar.** `validate()` percorre o arquivo inteiro e
devolve o veredito linha a linha **sem escrever nada** — nem no Postgres, nem
no Znuny. Importar 60 clientes e descobrir no 47º que a planilha tinha uma
coluna trocada é o tipo de erro que custa uma tarde.

**2. Erro numa linha não aborta as outras.** Cada linha é uma unidade. A
resposta diz o que foi criado, o que já existia e o que falhou, **com o número
da linha** — que é o que o operador precisa para consertar a planilha.

**3. Senha não entra por arquivo.** Uma coluna `password` num CSV vira senha em
texto claro no disco de quem exportou, no anexo do e-mail que mandou a
planilha, e no histórico do navegador. O importador **recusa** o arquivo que
tenha essa coluna, com a explicação — e gera uma senha por usuário, devolvida
uma única vez na resposta.
"""

from __future__ import annotations

import csv
import io
import secrets
import string
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar.domain.onboarding_service import (
    NewOnboarding,
    OnboardingConflict,
    OnboardingService,
)
from gerti_sidecar.integrations import znuny_customer_admin as gi
from gerti_sidecar.models import PortalUserRole, Tenant, ZnunyInstance
from gerti_sidecar.models.enums import PortalRole

# Cap de tamanho e de linhas. Não é paranoia: o importador chama o Znuny uma
# vez por linha, e um arquivo de 50 mil linhas viraria uma tempestade de
# requisições GI que ninguém consegue interromper no meio.
MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 2000

# Colunas que NUNCA podem vir num arquivo — ver o cabeçalho do módulo.
FORBIDDEN_COLUMNS = {"password", "senha", "pw", "pass"}

KINDS = ("tenants", "tenant_users")

_TENANT_COLUMNS = {
    "required": ["legal_name", "trade_name", "document", "subdomain", "znuny_customer_id"],
    "optional": [
        "display_name",
        "address_street",
        "address_number",
        "address_district",
        "address_city",
        "address_state",
        "address_zip",
        "contact_name",
        "contact_email",
        "contact_phone",
    ],
}
_USER_COLUMNS = {
    "required": ["email", "first_name", "last_name"],
    "optional": ["role", "phone", "mobile", "extension"],
}
COLUMNS = {"tenants": _TENANT_COLUMNS, "tenant_users": _USER_COLUMNS}


class ImportError_(ValueError):
    """Arquivo inteiro recusado (-> 422/413). Nada foi lido linha a linha."""


class FileTooLarge(ImportError_):
    """Acima do teto (-> 413)."""


@dataclass(slots=True)
class RowResult:
    line: int
    status: str  # ok | created | skipped | failed
    key: str = ""
    message: str = ""
    # Senha gerada, devolvida UMA vez. Nunca é relida de lugar nenhum depois.
    generated_password: str | None = None


@dataclass(slots=True)
class ImportReport:
    kind: str
    dry_run: bool
    total: int = 0
    valid: int = 0
    invalid: int = 0
    created: int = 0
    skipped: int = 0
    failed: int = 0
    rows: list[RowResult] = field(default_factory=list)


def _generate_password() -> str:
    """Senha inicial forte. Devolvida uma vez; nós não a guardamos em lugar nenhum."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16))


def template_csv(kind: str) -> str:
    """O modelo baixável. Cabeçalho + uma linha de exemplo comentada."""
    if kind not in COLUMNS:
        raise ImportError_(f"tipo desconhecido: {kind}")
    cols = COLUMNS[kind]["required"] + COLUMNS[kind]["optional"]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(cols)
    if kind == "tenants":
        writer.writerow(
            [
                "Acme Indústria LTDA",
                "Acme",
                "11.111.111/0001-11",
                "acme",
                "ACME",
                "Portal Acme",
                "Av. Afonso Pena",
                "1500",
                "Centro",
                "Belo Horizonte",
                "MG",
                "30130005",
                "Ana Souza",
                "ana@acme.example",
                "+553133330000",
            ]
        )
    else:
        writer.writerow(
            [
                "ana@acme.example",
                "Ana",
                "Souza",
                "helpdesk",
                "+553133330000",
                "",
                "204",
            ]
        )
    return buf.getvalue()


def parse_csv(raw: bytes, kind: str) -> list[dict[str, str]]:
    """Lê o arquivo inteiro e valida o CABEÇALHO. Erro aqui recusa tudo.

    Cabeçalho errado não é problema de uma linha — é arquivo errado, e não faz
    sentido processar 2000 linhas para dizer isso 2000 vezes.
    """
    if kind not in COLUMNS:
        raise ImportError_(f"tipo desconhecido: {kind}")
    if len(raw) > MAX_BYTES:
        raise FileTooLarge(f"arquivo acima de {MAX_BYTES // (1024 * 1024)} MB")

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportError_("arquivo não é UTF-8. Exporte a planilha como CSV UTF-8.") from exc

    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip().lower() for h in (reader.fieldnames or [])]
    if not header:
        raise ImportError_("arquivo vazio ou sem cabeçalho")

    forbidden = FORBIDDEN_COLUMNS & set(header)
    if forbidden:
        raise ImportError_(
            f"a coluna {sorted(forbidden)[0]!r} não é aceita: senha não trafega em "
            "planilha. O importador gera uma senha por usuário e a mostra uma única vez."
        )

    spec = COLUMNS[kind]
    missing = [c for c in spec["required"] if c not in header]
    if missing:
        raise ImportError_(
            f"faltam as colunas obrigatórias: {', '.join(missing)}. "
            f"Esperado: {', '.join(spec['required'] + spec['optional'])}"
        )

    rows: list[dict[str, str]] = []
    for row in reader:
        if len(rows) >= MAX_ROWS:
            raise ImportError_(f"arquivo acima de {MAX_ROWS} linhas")
        rows.append({(k or "").strip().lower(): (v or "").strip() for k, v in row.items()})
    return rows


def _validate_row(kind: str, row: dict[str, str]) -> str | None:
    """`None` = linha boa. String = o motivo, em português, para a tela mostrar."""
    for col in COLUMNS[kind]["required"]:
        if not row.get(col):
            return f"'{col}' está vazio"
    if kind == "tenants":
        sub = row["subdomain"]
        if not sub.islower() or " " in sub:
            return "subdomínio deve ser minúsculo e sem espaço"
    else:
        email = row["email"]
        if "@" not in email or "." not in email.split("@")[-1]:
            return f"e-mail inválido: {email}"
        role = row.get("role") or "helpdesk"
        if role not in ("admin", "helpdesk"):
            return f"papel desconhecido: {role} (use admin ou helpdesk)"
    return None


class ImportService:
    def __init__(self, admin_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = admin_factory

    async def validate(self, kind: str, raw: bytes) -> ImportReport:
        """Simulação: percorre tudo e **não grava nada**, em lugar nenhum."""
        rows = parse_csv(raw, kind)
        report = ImportReport(kind=kind, dry_run=True, total=len(rows))
        seen: set[str] = set()
        for i, row in enumerate(rows, start=2):  # linha 1 é o cabeçalho
            problem = _validate_row(kind, row)
            key = row.get("znuny_customer_id") or row.get("email") or ""
            if problem is None:
                # Duplicata DENTRO do próprio arquivo — o banco pegaria depois,
                # mas dizer agora evita meia importação.
                dedupe = (row.get("subdomain") or row.get("email") or "").lower()
                if dedupe and dedupe in seen:
                    problem = f"repetida no próprio arquivo: {dedupe}"
                else:
                    seen.add(dedupe)
            if problem is None:
                report.valid += 1
                report.rows.append(RowResult(line=i, status="ok", key=key))
            else:
                report.invalid += 1
                report.rows.append(RowResult(line=i, status="failed", key=key, message=problem))
        return report

    async def import_tenants(self, raw: bytes, *, created_by: str) -> ImportReport:
        """Cria os clientes, linha a linha. Idempotente por `znuny_customer_id`.

        Reusa o `OnboardingService`, que já é idempotente — reexecutar o mesmo
        arquivo devolve `skipped`, nunca duplicata.
        """
        rows = parse_csv(raw, "tenants")
        report = ImportReport(kind="tenants", dry_run=False, total=len(rows))

        async with self._factory() as s:
            instance = (
                await s.execute(select(ZnunyInstance).order_by(ZnunyInstance.created_at).limit(1))
            ).scalar_one_or_none()
        if instance is None:
            raise ImportError_("nenhuma instância Znuny registrada")

        service = OnboardingService(self._factory)
        for i, row in enumerate(rows, start=2):
            problem = _validate_row("tenants", row)
            if problem:
                report.failed += 1
                report.rows.append(
                    RowResult(
                        line=i, status="failed", key=row.get("subdomain", ""), message=problem
                    )
                )
                continue

            async with self._factory() as s:
                exists = await s.scalar(
                    select(Tenant.id).where(Tenant.znuny_customer_id == row["znuny_customer_id"])
                )
            if exists is not None:
                report.skipped += 1
                report.rows.append(
                    RowResult(
                        line=i,
                        status="skipped",
                        key=row["znuny_customer_id"],
                        message="já cadastrado",
                    )
                )
                continue

            try:
                await service.onboard(
                    NewOnboarding(
                        legal_name=row["legal_name"],
                        trade_name=row["trade_name"],
                        document=row["document"],
                        subdomain=row["subdomain"],
                        znuny_customer_id=row["znuny_customer_id"],
                        znuny_instance_id=instance.id,
                        display_name=row.get("display_name") or row["trade_name"],
                        primary_color="#2563EB",
                        accent_color="#1E40AF",
                        support_email=row.get("contact_email") or None,
                        logo_url=None,
                        users=[],
                        created_by=created_by,
                        address_street=row.get("address_street") or None,
                        address_number=row.get("address_number") or None,
                        address_district=row.get("address_district") or None,
                        address_city=row.get("address_city") or None,
                        address_state=row.get("address_state") or None,
                        address_zip=row.get("address_zip") or None,
                        contact_name=row.get("contact_name") or None,
                        contact_email=row.get("contact_email") or None,
                        contact_phone=row.get("contact_phone") or None,
                    )
                )
            except (OnboardingConflict, gi.ZnunyWriteError, gi.ZnunyUnavailable) as exc:
                # Falha isolada: as outras linhas seguem.
                report.failed += 1
                report.rows.append(
                    RowResult(
                        line=i, status="failed", key=row["znuny_customer_id"], message=str(exc)
                    )
                )
                continue

            report.created += 1
            report.rows.append(RowResult(line=i, status="created", key=row["znuny_customer_id"]))
        return report

    async def import_users(
        self, raw: bytes, *, tenant_id: uuid.UUID, created_by: str
    ) -> ImportReport:
        """Cria as pessoas de UM cliente. Senha gerada, devolvida uma vez."""
        rows = parse_csv(raw, "tenant_users")
        report = ImportReport(kind="tenant_users", dry_run=False, total=len(rows))

        async with self._factory() as s:
            tenant = await s.get(Tenant, tenant_id)
        if tenant is None:
            raise ImportError_("cliente não encontrado")
        customer_id = tenant.znuny_customer_id

        for i, row in enumerate(rows, start=2):
            problem = _validate_row("tenant_users", row)
            if problem:
                report.failed += 1
                report.rows.append(
                    RowResult(line=i, status="failed", key=row.get("email", ""), message=problem)
                )
                continue

            login = row["email"].lower()
            async with self._factory() as s:
                exists = await s.scalar(
                    select(PortalUserRole.id).where(
                        PortalUserRole.tenant_id == tenant_id,
                        func.lower(PortalUserRole.customer_login) == login,
                    )
                )
            if exists is not None:
                report.skipped += 1
                report.rows.append(
                    RowResult(line=i, status="skipped", key=login, message="já cadastrado")
                )
                continue

            password = _generate_password()
            try:
                await gi.create_customer_user(
                    login=row["email"],
                    email=row["email"],
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    customer_id=customer_id,
                    phone=row.get("phone") or None,
                    mobile=row.get("mobile") or None,
                )
                await gi.set_password(row["email"], password)
            except (gi.ZnunyWriteError, gi.ZnunyUnavailable) as exc:
                report.failed += 1
                report.rows.append(RowResult(line=i, status="failed", key=login, message=str(exc)))
                continue

            async with self._factory() as s:
                async with s.begin():
                    s.add(
                        PortalUserRole(
                            tenant_id=tenant_id,
                            customer_login=login,
                            role=PortalRole(row.get("role") or "helpdesk"),
                            extension=row.get("extension") or None,
                        )
                    )
            report.created += 1
            report.rows.append(
                RowResult(line=i, status="created", key=login, generated_password=password)
            )
        return report


def report_as_dict(report: ImportReport) -> dict[str, Any]:
    return {
        "kind": report.kind,
        "dry_run": report.dry_run,
        "total": report.total,
        "valid": report.valid,
        "invalid": report.invalid,
        "created": report.created,
        "skipped": report.skipped,
        "failed": report.failed,
        "rows": [
            {
                "line": r.line,
                "status": r.status,
                "key": r.key,
                "message": r.message,
                "generated_password": r.generated_password,
            }
            for r in report.rows
        ],
    }
