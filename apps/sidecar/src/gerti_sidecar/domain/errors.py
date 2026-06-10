"""Domain exceptions for the contract engine."""

from __future__ import annotations


class DomainError(Exception):
    """Base for contract-domain errors."""


class ContractValidationError(DomainError):
    """Invalid contract input or violated invariant."""


class ConsumptionError(DomainError):
    """Invalid consumption recording."""


class CycleError(DomainError):
    """Invalid cycle operation."""


class InvoiceError(DomainError):
    """Operação inválida sobre fatura (transição proibida, fatura inexistente) -> 404/409."""


class InvoiceAlreadyExists(InvoiceError):
    """Já existe uma fatura para este ciclo (1 por ciclo) -> 409."""


class CycleNotClosable(InvoiceError):
    """Ciclo não está num estado faturável (ex.: ainda aberto) -> 409."""


class CsatError(DomainError):
    """Invalid CSAT submission (ticket não encontrado/posse, score inválido) -> 404/422."""


class TicketNotClosed(CsatError):
    """CSAT só é permitido em ticket fechado -> 422."""


class CsatAlreadyExists(CsatError):
    """Já existe uma resposta CSAT para este ticket (UNIQUE) -> 409."""


class AiRateLimited(DomainError):
    """Cliente excedeu o limite de chamadas do assistente de IA na janela -> 429 (#1S)."""


class EnrollError(DomainError):
    """Erro no enrollment/heartbeat do agente de inventário (#1R-a)."""


class EnrollTokenInvalid(EnrollError):
    """Token de enroll inexistente/desabilitado, ou agent_secret desconhecido -> 401."""


class AgentRevoked(EnrollError):
    """Device revogado pelo operador: heartbeat recusado -> 401."""
