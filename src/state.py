from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .models import Severity


@dataclass(frozen=True)
class ResourceState:
    last_notification_at: Optional[datetime] = None
    last_stop_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    last_decision_severity: Severity = Severity.OK


@dataclass
class EngineState:
    resources: dict[str, ResourceState] = field(default_factory=dict)


def make_resource_key(project_id: str, resource_id: str) -> str:
    return f"{project_id}:{resource_id}"


def get_resource_state(
    state: EngineState,
    project_id: str,
    resource_id: str,
) -> ResourceState:
    key = make_resource_key(project_id, resource_id)
    return state.resources.get(key, ResourceState())


def save_resource_state(
    state: EngineState,
    project_id: str,
    resource_id: str,
    resource_state: ResourceState,
) -> None:
    key = make_resource_key(project_id, resource_id)
    state.resources[key] = resource_state