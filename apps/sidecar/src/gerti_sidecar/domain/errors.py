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


class CsatError(DomainError):
    """Invalid CSAT submission (ticket não encontrado/posse, score inválido) -> 404/422."""


class TicketNotClosed(CsatError):
    """CSAT só é permitido em ticket fechado -> 422."""


class CsatAlreadyExists(CsatError):
    """Já existe uma resposta CSAT para este ticket (UNIQUE) -> 409."""
