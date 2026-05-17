from gerti_sidecar.models.enums import (
    BillingStatus,
    ContractStatus,
    ContractType,
    CycleKind,
    CycleStatus,
    GlosaStatus,
)


def test_enum_values_match_db_contract():
    assert [e.value for e in ContractType] == [
        "closed_value",
        "credit_brl",
        "credit_shared",
        "hour_bank",
        "saas_product",
        "service_count",
    ]
    assert [e.value for e in ContractStatus] == [
        "draft",
        "active",
        "suspended",
        "expired",
        "terminated",
    ]
    assert [e.value for e in CycleKind] == ["billing", "closing"]
    assert [e.value for e in CycleStatus] == ["open", "closed", "invoiced"]
    assert [e.value for e in GlosaStatus] == ["pending", "approved", "rejected"]
    assert [e.value for e in BillingStatus] == ["pending", "approved", "billed", "disputed"]
    assert ContractType.hour_bank == "hour_bank"  # StrEnum behaviour
