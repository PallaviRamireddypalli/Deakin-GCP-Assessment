from __future__ import annotations

from .approvals import Approval
from .approvals import ProvisioningRequest
from .models import Project
from .models import RuntimeSnapshot
from .ports import NotificationMessage
from .state import EngineState


class MemoryProjectDiscovery:
    def __init__(self, projects: list[Project]) -> None:
        self.projects = list(projects)

    def discover_projects(self) -> list[Project]:
        return list(self.projects)


class MemoryApprovalRepository:
    def __init__(self, approvals: list[Approval]) -> None:
        self.approvals = list(approvals)

    def list_approvals(self) -> list[Approval]:
        return list(self.approvals)


class MemoryProvisioningRequestRepository:
    def __init__(self, requests: list[ProvisioningRequest]) -> None:
        self.requests = list(requests)

    def list_requests(self) -> list[ProvisioningRequest]:
        return list(self.requests)


class MemoryRuntimeInventory:
    def __init__(self, snapshots: list[RuntimeSnapshot]) -> None:
        self.snapshots = list(snapshots)

    def list_runtime_snapshots(self) -> list[RuntimeSnapshot]:
        return list(self.snapshots)


class MemoryRuntimeController:
    def __init__(self) -> None:
        self.stops: list[tuple[str, str, tuple[str, ...]]] = []

    def stop_runtime(
        self,
        project_id: str,
        resource_id: str,
        reasons: tuple[str, ...],
    ) -> None:
        self.stops.append((project_id, resource_id, reasons))


class MemoryNotifier:
    def __init__(self) -> None:
        self.messages: list[NotificationMessage] = []

    def notify(self, message: NotificationMessage) -> None:
        self.messages.append(message)

    def escalate(self, message: NotificationMessage) -> None:
        self.messages.append(message)


class MemoryStateStore:
    def __init__(self, initial_state: EngineState | None = None) -> None:
        self.state = initial_state or EngineState()

    def load_state(self) -> EngineState:
        return self.state

    def save_state(self, state: EngineState) -> None:
        self.state = state


class MemoryManagedProjectRegistry:
    def __init__(self, managed_project_ids: set[str] | None = None) -> None:
        self.managed_project_ids = set(managed_project_ids or set())

    def load_managed_project_ids(self) -> set[str]:
        return set(self.managed_project_ids)

    def replace_managed_project_ids(self, project_ids: set[str]) -> None:
        self.managed_project_ids = set(project_ids)