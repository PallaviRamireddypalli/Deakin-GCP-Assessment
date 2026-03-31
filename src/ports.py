from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .approvals import Approval
from .approvals import ProvisioningRequest
from .models import Project
from .models import RuntimeSnapshot
from .state import EngineState


@dataclass(frozen=True)
class NotificationMessage:
    category: str
    subject: str
    body: str
    targets: tuple[str, ...]


class ProjectDiscoveryPort(Protocol):
    def discover_projects(self) -> list[Project]:
        ...


class ApprovalRepositoryPort(Protocol):
    def list_approvals(self) -> list[Approval]:
        ...


class ProvisioningRequestRepositoryPort(Protocol):
    def list_requests(self) -> list[ProvisioningRequest]:
        ...


class RuntimeInventoryPort(Protocol):
    def list_runtime_snapshots(self) -> list[RuntimeSnapshot]:
        ...


class RuntimeControllerPort(Protocol):
    def stop_runtime(
        self,
        project_id: str,
        resource_id: str,
        reasons: tuple[str, ...],
    ) -> None:
        ...


class NotifierPort(Protocol):
    def notify(self, message: NotificationMessage) -> None:
        ...

    def escalate(self, message: NotificationMessage) -> None:
        ...


class StateStorePort(Protocol):
    def load_state(self) -> EngineState:
        ...

    def save_state(self, state: EngineState) -> None:
        ...


class ManagedProjectRegistryPort(Protocol):
    def load_managed_project_ids(self) -> set[str]:
        ...

    def replace_managed_project_ids(self, project_ids: set[str]) -> None:
        ...