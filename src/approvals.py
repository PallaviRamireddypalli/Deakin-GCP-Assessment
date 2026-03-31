from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Optional


class RequestStatus(StrEnum):
    ALLOW = "ALLOW"
    ALLOW_BY_EXCEPTION = "ALLOW_BY_EXCEPTION"
    DENY = "DENY"


@dataclass(frozen=True)
class Approval:
    approval_id: str
    project_id: str
    valid_from: datetime
    valid_to: datetime
    approved_products: tuple[str, ...]
    approved_machine_prefixes: tuple[str, ...] = ()
    approved_accelerators: tuple[str, ...] = ()
    approved_max_hourly_burn_aud: Optional[float] = None
    requested_by: str = ""
    approved_by: str = ""
    active: bool = True


@dataclass(frozen=True)
class ProvisioningRequest:
    request_id: str
    project_id: str
    product: str
    machine_type: str
    region: str
    requested_at: datetime
    requested_by: str
    estimated_hourly_burn_aud: float
    accelerator_type: Optional[str] = None


@dataclass(frozen=True)
class RequestDecision:
    project_id: str
    request_id: str
    status: RequestStatus
    allow: bool
    notify: bool
    reasons: tuple[str, ...]
    matched_approval_id: Optional[str]


def normalize_token(value: Optional[str]) -> str:
    return (value or "").strip().upper()


def product_in_list(product: str, allowed_products: tuple[str, ...]) -> bool:
    wanted = normalize_token(product)
    return wanted in {normalize_token(item) for item in allowed_products}


def accelerator_in_list(accelerator_type: Optional[str], allowed_accelerators: tuple[str, ...]) -> bool:
    wanted = normalize_token(accelerator_type)
    return wanted in {normalize_token(item) for item in allowed_accelerators}


def approval_is_active(approval: Approval, when: datetime) -> bool:
    return approval.active and approval.valid_from <= when <= approval.valid_to