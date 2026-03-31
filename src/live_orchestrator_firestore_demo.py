from __future__ import annotations

from .firestore_state_store import FirestoreManagedProjectRegistry
from .firestore_state_store import FirestoreStateStore
from .gcp_project_discovery import GcpProjectDiscovery
from .local_adapters import MemoryApprovalRepository
from .local_adapters import MemoryNotifier
from .local_adapters import MemoryProvisioningRequestRepository
from .local_adapters import MemoryRuntimeController
from .local_adapters import MemoryRuntimeInventory
from .orchestrator import orchestrate_cycle


def main() -> None:
    organization_id = "YOUR_ORG_ID"

    project_discovery = GcpProjectDiscovery(
        organization_id=organization_id,
        profile_path="data/project_profiles.json",
    )

    approval_repository = MemoryApprovalRepository([])
    request_repository = MemoryProvisioningRequestRepository([])
    runtime_inventory = MemoryRuntimeInventory([])
    runtime_controller = MemoryRuntimeController()
    notifier = MemoryNotifier()

    state_store = FirestoreStateStore()
    managed_registry = FirestoreManagedProjectRegistry()

    result = orchestrate_cycle(
        project_discovery=project_discovery,
        approval_repository=approval_repository,
        request_repository=request_repository,
        runtime_inventory=runtime_inventory,
        runtime_controller=runtime_controller,
        notifier=notifier,
        state_store=state_store,
        managed_project_registry=managed_registry,
    )

    print("=== Live Orchestrator with Firestore ===")
    print(f"To onboard: {result.registry_sync.to_onboard}")
    print(f"To offboard: {result.registry_sync.to_offboard}")
    print(f"Managed registry now: {managed_registry.load_managed_project_ids()}")
    print(f"Request decisions: {len(result.request_decisions)}")
    print(f"Runtime decisions: {len(result.runtime_decisions)}")
    print(f"Action plans: {len(result.action_plans)}")
    print(f"Notifications emitted: {len(notifier.messages)}")
    print(f"Stop actions issued: {len(runtime_controller.stops)}")


if __name__ == "__main__":
    main()