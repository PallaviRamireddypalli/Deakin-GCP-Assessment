from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .firestore_state_store import FirestoreManagedProjectRegistry
from .firestore_state_store import FirestoreStateStore
from .gcp_project_discovery import GcpProjectDiscovery
from .local_adapters import MemoryApprovalRepository
from .local_adapters import MemoryNotifier
from .local_adapters import MemoryProvisioningRequestRepository
from .local_adapters import MemoryRuntimeController
from .local_adapters import MemoryRuntimeInventory
from .models import ResourceStatus
from .models import RuntimeSnapshot
from .orchestrator import orchestrate_cycle


def build_runtime_snapshot(minutes_offset: int = 0) -> RuntimeSnapshot:
    base_time = datetime(2026, 2, 22, 18, 0, tzinfo=timezone.utc) + timedelta(minutes=minutes_offset)

    return RuntimeSnapshot(
        resource_id="runtime-live-demo-001",
        project_id="YOUR_PROJECT_ID",
        product="COLAB_ENTERPRISE",
        machine_type="a2-highgpu-1g",
        region="australia-southeast1",
        accelerator_type="A100",
        status=ResourceStatus.RUNNING,
        connected=True,
        observed_at=base_time,
        started_at=base_time - timedelta(hours=9),
        last_activity_at=base_time - timedelta(hours=9),
        hourly_burn_rate_aud=12.0,
    )


def main() -> None:
    organization_id = "YOUR_ORG_ID"

    print("=== RUN 1 ===")

    project_discovery = GcpProjectDiscovery(
        organization_id=organization_id,
        profile_path="data/project_profiles.json",
    )

    approval_repository = MemoryApprovalRepository([])
    request_repository = MemoryProvisioningRequestRepository([])
    runtime_inventory = MemoryRuntimeInventory([build_runtime_snapshot(minutes_offset=0)])
    runtime_controller = MemoryRuntimeController()
    notifier = MemoryNotifier()
    state_store = FirestoreStateStore()
    managed_registry = FirestoreManagedProjectRegistry()

    result_1 = orchestrate_cycle(
        project_discovery=project_discovery,
        approval_repository=approval_repository,
        request_repository=request_repository,
        runtime_inventory=runtime_inventory,
        runtime_controller=runtime_controller,
        notifier=notifier,
        state_store=state_store,
        managed_project_registry=managed_registry,
    )

    print(f"Runtime decisions: {len(result_1.runtime_decisions)}")
    print(f"Action plans: {len(result_1.action_plans)}")
    print(f"Notifications emitted: {len(notifier.messages)}")
    print(f"Stop actions issued: {len(runtime_controller.stops)}")

    for message in notifier.messages:
        print(f"NOTIFY: {message.subject} | targets={message.targets}")

    print()
    print("=== RUN 2 (45 minutes later) ===")

    runtime_inventory_2 = MemoryRuntimeInventory([build_runtime_snapshot(minutes_offset=45)])
    runtime_controller_2 = MemoryRuntimeController()
    notifier_2 = MemoryNotifier()

    result_2 = orchestrate_cycle(
        project_discovery=project_discovery,
        approval_repository=approval_repository,
        request_repository=request_repository,
        runtime_inventory=runtime_inventory_2,
        runtime_controller=runtime_controller_2,
        notifier=notifier_2,
        state_store=state_store,
        managed_project_registry=managed_registry,
    )

    print(f"Runtime decisions: {len(result_2.runtime_decisions)}")
    print(f"Action plans: {len(result_2.action_plans)}")
    print(f"Notifications emitted: {len(notifier_2.messages)}")
    print(f"Stop actions issued: {len(runtime_controller_2.stops)}")

    for message in notifier_2.messages:
        print(f"NOTIFY: {message.subject} | targets={message.targets}")


if __name__ == "__main__":
    main()