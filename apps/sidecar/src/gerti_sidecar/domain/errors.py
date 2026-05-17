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
