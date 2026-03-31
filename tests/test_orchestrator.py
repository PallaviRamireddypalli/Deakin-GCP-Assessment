from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from src.local_adapters import MemoryApprovalRepository
from src.local_adapters import MemoryManagedProjectRegistry
from src.local_adapters import MemoryNotifier
from src.local_adapters import MemoryProjectDiscovery
from src.local_adapters import MemoryProvisioningRequestRepository
from src.local_adapters import MemoryRuntimeController
from src.local_adapters import MemoryRuntimeInventory
from src.local_adapters import MemoryStateStore
from src.orchestrator import orchestrate_cycle
from src.simulator import load_scenario


def test_orchestrator_runs_student_a_flow_without_changing_core_logic():
    scenario = load_scenario(Path("data/scenario_student_a.json"))

    project_discovery = MemoryProjectDiscovery(list(scenario.projects))
    approval_repository = MemoryApprovalRepository(list(scenario.approvals))
    request_repository = MemoryProvisioningRequestRepository(list(scenario.provisioning_requests))
    runtime_inventory = MemoryRuntimeInventory(list(scenario.runtime_snapshots))
    runtime_controller = MemoryRuntimeController()
    notifier = MemoryNotifier()
    state_store = MemoryStateStore()
    managed_registry = MemoryManagedProjectRegistry(set(scenario.managed_project_ids))

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

    assert result.registry_sync.to_onboard == ("phd-student-a", "teaching-unit-01")
    assert result.registry_sync.to_offboard == ("legacy-project",)

    assert managed_registry.load_managed_project_ids() == {
        "phd-student-a",
        "teaching-unit-01",
    }

    assert ("phd-student-a", "runtime-001") == (
        runtime_controller.stops[0][0],
        runtime_controller.stops[0][1],
    )

    subjects = {message.subject for message in notifier.messages}
    assert "Provisioning denied: req-student-a" in subjects
    assert "Runtime action required: runtime-001" in subjects


def test_orchestrator_unknown_runtime_notifies_platform_ops():
    scenario = load_scenario(Path("data/scenario_edge_cases.json"))

    project_discovery = MemoryProjectDiscovery(list(scenario.projects))
    approval_repository = MemoryApprovalRepository(list(scenario.approvals))
    request_repository = MemoryProvisioningRequestRepository(list(scenario.provisioning_requests))
    runtime_inventory = MemoryRuntimeInventory(list(scenario.runtime_snapshots))
    runtime_controller = MemoryRuntimeController()
    notifier = MemoryNotifier()
    state_store = MemoryStateStore()
    managed_registry = MemoryManagedProjectRegistry(set(scenario.managed_project_ids))

    orchestrate_cycle(
        project_discovery=project_discovery,
        approval_repository=approval_repository,
        request_repository=request_repository,
        runtime_inventory=runtime_inventory,
        runtime_controller=runtime_controller,
        notifier=notifier,
        state_store=state_store,
        managed_project_registry=managed_registry,
    )

    assert any(
        message.subject == "Runtime action required: runtime-unknown"
        and message.targets == ("platform-ops@example.edu",)
        for message in notifier.messages
    )


def test_orchestrator_escalates_repeated_critical_runtime_on_second_cycle():
    scenario = load_scenario(Path("data/scenario_student_a.json"))

    project_discovery = MemoryProjectDiscovery(list(scenario.projects))
    approval_repository = MemoryApprovalRepository(list(scenario.approvals))
    request_repository = MemoryProvisioningRequestRepository(list(scenario.provisioning_requests))
    runtime_inventory = MemoryRuntimeInventory(list(scenario.runtime_snapshots))
    runtime_controller = MemoryRuntimeController()
    notifier = MemoryNotifier()
    state_store = MemoryStateStore()
    managed_registry = MemoryManagedProjectRegistry(set(scenario.managed_project_ids))

    orchestrate_cycle(
        project_discovery=project_discovery,
        approval_repository=approval_repository,
        request_repository=request_repository,
        runtime_inventory=runtime_inventory,
        runtime_controller=runtime_controller,
        notifier=notifier,
        state_store=state_store,
        managed_project_registry=managed_registry,
    )

    later_snapshots = []
    for snapshot in scenario.runtime_snapshots:
        if snapshot.resource_id == "runtime-001":
            later_snapshots.append(
                replace(
                    snapshot,
                    observed_at=snapshot.observed_at + timedelta(minutes=45),
                )
            )
        else:
            shifted_last_activity = snapshot.last_activity_at
            if shifted_last_activity is not None:
                shifted_last_activity = shifted_last_activity + timedelta(minutes=45)

            later_snapshots.append(
                replace(
                    snapshot,
                    observed_at=snapshot.observed_at + timedelta(minutes=45),
                    last_activity_at=shifted_last_activity,
                )
            )

    second_runtime_inventory = MemoryRuntimeInventory(later_snapshots)
    empty_request_repository = MemoryProvisioningRequestRepository([])

    orchestrate_cycle(
        project_discovery=project_discovery,
        approval_repository=approval_repository,
        request_repository=empty_request_repository,
        runtime_inventory=second_runtime_inventory,
        runtime_controller=runtime_controller,
        notifier=notifier,
        state_store=state_store,
        managed_project_registry=managed_registry,
    )

    assert any(
        message.subject == "Runtime escalation: runtime-001"
        and message.category == "RUNTIME_ESCALATION"
        for message in notifier.messages
    )