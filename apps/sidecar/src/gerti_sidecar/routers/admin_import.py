"""/v1/admin/import/* — carga em lote por CSV (T-R8.1..8.4, R8).

Dois passos, sempre nessa ordem, e o primeiro é o que evita a tarde perdida:

  • `POST /import/{kind}/validate` — **simula**. Percorre o arquivo inteiro e
    devolve o veredito linha a linha sem gravar nada, em lugar nenhum.
  • `POST /import/{kind}` — executa, idempotente por linha. Erro numa linha não
    aborta as demais, e a resposta traz o número da linha que falhou.

`kind` é allowlist fechada (`tenants`, `tenant_users`): chave fora dela é 404,
sem nunca virar consulta.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.domain import audit_service
from gerti_sidecar.domain.import_service import (
    KINDS,
    MAX_BYTES,
    FileTooLarge,
    ImportError_,
    ImportService,
    report_as_dict,
    template_csv,
)

router = APIRouter(prefix="/admin/import", tags=["admin"])


def _check_kind(kind: str) -> None:
    if kind not in KINDS:
        raise HTTPException(status_code=404, detail="import_kind_not_found")


def _service() -> ImportService:
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")
    return ImportService(db.AdminSessionLocal)


async def _read(file: UploadFile) -> bytes:
    raw = await file.read()
    # Teto checado ANTES de qualquer parse: um arquivo de 500 MB não pode nem
    # chegar a virar string na memória.
    if len(raw) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="arquivo grande demais (máx. 5 MB)")
    return raw


@router.get("/{kind}/template", response_class=PlainTextResponse)
async def get_template(
    kind: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> PlainTextResponse:
    """O modelo baixável — cabeçalho certo é metade da importação."""
    _check_kind(kind)
    return PlainTextResponse(
        template_csv(kind),
        media_type="text/csv; charset=utf-8",
        headers={"content-disposition": f'attachment; filename="modelo-{kind}.csv"'},
    )


@router.post("/{kind}/validate")
async def validate_import(
    kind: str,
    file: UploadFile = File(...),
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> dict[str, Any]:
    """Simulação. **Não grava nada** — nem no Postgres, nem no Znuny."""
    _check_kind(kind)
    raw = await _read(file)
    try:
        report = await _service().validate(kind, raw)
    except FileTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ImportError_ as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return report_as_dict(report)


@router.post("/{kind}")
async def run_import(
    kind: str,
    request: Request,
    file: UploadFile = File(...),
    tenant_id: str | None = None,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> dict[str, Any]:
    _check_kind(kind)
    raw = await _read(file)
    service = _service()

    try:
        if kind == "tenants":
            report = await service.import_tenants(raw, created_by=admin["agent_login"])
        else:
            if not tenant_id:
                raise HTTPException(status_code=422, detail="informe o cliente dono dos usuários")
            try:
                tid = uuid.UUID(tenant_id)
            except (ValueError, AttributeError):
                raise HTTPException(status_code=404, detail="tenant_not_found") from None
            report = await service.import_users(raw, tenant_id=tid, created_by=admin["agent_login"])
    except FileTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ImportError_ as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Uma linha de auditoria por LOTE, com a contagem. As senhas geradas ficam
    # de fora — elas vão para a tela uma vez e não são guardadas em lugar nenhum.
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=uuid.UUID(tenant_id) if (kind == "tenant_users" and tenant_id) else None,
        action="create",
        entity=f"import:{kind}",
        entity_id="",
        description=(
            f"importação de {kind}: {report.created} criado(s), "
            f"{report.skipped} já existia(m), {report.failed} falhou(aram)"
        ),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={
            "total": report.total,
            "created": report.created,
            "skipped": report.skipped,
            "failed": report.failed,
            "failed_lines": [r.line for r in report.rows if r.status == "failed"][:50],
        },
    )
    return report_as_dict(report)
