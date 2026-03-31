from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Optional


class UseCase(StrEnum):
    PHD_RESEARCH = "PHD_RESEARCH"
    TEACHING_AND_LEARNING = "TEACHING_AND_LEARNING"
    GENERAL_RESEARCH = "GENERAL_RESEARCH"
    PROFESSIONAL_STAFF = "PROFESSIONAL_STAFF"
    UNKNOWN = "UNKNOWN"


class PrincipalMode(StrEnum):
    ONE_TO_ONE = "ONE_TO_ONE"
    ONE_TO_MANY = "ONE_TO_MANY"


class ResourceStatus(StrEnum):
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"


class Severity(StrEnum):
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class Project:
    project_id: str
    name: str
    folder_path: tuple[str, ...]
    use_case: UseCase
    principal_mode: PrincipalMode
    principals: tuple[str, ...]
    budget_monthly_aud: float
    budget_spent_aud: float
    active: bool = True
    planned_products: tuple[str, ...] = ()
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeSnapshot:
    resource_id: str
    project_id: str
    product: str
    machine_type: str
    region: str
    accelerator_type: Optional[str]
    status: ResourceStatus
    connected: bool
    observed_at: datetime
    started_at: datetime
    last_activity_at: Optional[datetime]
    hourly_burn_rate_aud: float


@dataclass(frozen=True)
class Decision:
    project_id: str
    resource_id: str
    severity: Severity
    stop_now: bool
    notify: bool
    reasons: tuple[str, ...]
    risk_score: int
    idle_minutes: float
    adaptive_idle_threshold_minutes: float
    notification_targets: tuple[str, ...]