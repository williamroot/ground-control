"""Modelos SQLAlchemy do sidecar (schema gerti)."""

from gerti_sidecar.models.agent_inventory import AgentEnrollToken, DeviceAgent
from gerti_sidecar.models.agent_timer import AgentTimer
from gerti_sidecar.models.ai_generation_log import AiGenerationLog
from gerti_sidecar.models.audit_log import AuditLog
from gerti_sidecar.models.automation import AutomationRule, AutomationRun
from gerti_sidecar.models.base import Base
from gerti_sidecar.models.catalog import ServiceCatalogItem, SharedCreditPool
from gerti_sidecar.models.catalog_item import CatalogItem
from gerti_sidecar.models.consumption import ConsumptionEvent, Glosa
from gerti_sidecar.models.consumption_orphan import ConsumptionOrphan
from gerti_sidecar.models.contract import Contract, ContractBillingParty
from gerti_sidecar.models.contract_policy import (
    ContractAdjustmentRule,
    ContractRenewalPolicy,
)
from gerti_sidecar.models.contract_scope import ContractScopeCi, ContractScopeService
from gerti_sidecar.models.contratacao import (
    AsaasWebhookEvent,
    CheckoutSession,
    Payment,
    PaymentProviderAccount,
    Plan,
)
from gerti_sidecar.models.csat import CsatResponse
from gerti_sidecar.models.cycle import ContractCycle
from gerti_sidecar.models.invoice import Invoice, InvoiceLine
from gerti_sidecar.models.kb import KbArticle
from gerti_sidecar.models.notification import Notification
from gerti_sidecar.models.portal_user_role import PortalUserRole
from gerti_sidecar.models.recurring_task import RecurringTask, RecurringTaskRun
from gerti_sidecar.models.sync_cursor import ConsumptionSyncCursor
from gerti_sidecar.models.tenant import Tenant
from gerti_sidecar.models.tenant_branding import TenantBranding
from gerti_sidecar.models.tenant_queue import TenantQueue
from gerti_sidecar.models.ticket_link import TicketContractLink
from gerti_sidecar.models.user_preference import UserPreference
from gerti_sidecar.models.worker_heartbeat import WorkerHeartbeat
from gerti_sidecar.models.znuny_instance import ZnunyInstance

__all__ = [
    "AgentEnrollToken",
    "AgentTimer",
    "AiGenerationLog",
    "AsaasWebhookEvent",
    "AuditLog",
    "AutomationRule",
    "AutomationRun",
    "Base",
    "CatalogItem",
    "CheckoutSession",
    "ConsumptionEvent",
    "ConsumptionOrphan",
    "ConsumptionSyncCursor",
    "Contract",
    "ContractAdjustmentRule",
    "ContractBillingParty",
    "ContractCycle",
    "ContractRenewalPolicy",
    "ContractScopeCi",
    "ContractScopeService",
    "CsatResponse",
    "DeviceAgent",
    "Glosa",
    "Invoice",
    "InvoiceLine",
    "KbArticle",
    "Notification",
    "Payment",
    "PaymentProviderAccount",
    "Plan",
    "PortalUserRole",
    "RecurringTask",
    "RecurringTaskRun",
    "ServiceCatalogItem",
    "SharedCreditPool",
    "Tenant",
    "TenantBranding",
    "TenantQueue",
    "TicketContractLink",
    "UserPreference",
    "WorkerHeartbeat",
    "ZnunyInstance",
]
