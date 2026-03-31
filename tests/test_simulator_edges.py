from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from src.actions import ActionType
from src.approvals import RequestStatus
from src.models import Severity
from src.simulator import ScenarioInput
from src.simulator import load_scenario
from src.simulator import run_scenario
from src.simulator import run_scenario_with_state


def test_edge_case_scenario_covers_remaining_blind_spots():
    scenario = load_scenario(Path("data/scenario_edge_cases.json"))
    result = run_scenario(scenario)

    assert set(result.registry_sync.to_onboard) == {
        "cpu-project",
        "expired-approval-project",
        "phd-budget-exhausted",
        "region-project",
        "teaching-default-budget",
    }
    assert set(result.registry_sync.to_offboard) == {
        "legacy-project",
        "stale-project",
    }

    request_index = {item.request_id: item for item in result.request_decisions}
    runtime_index = {item.resource_id: item for item in result.runtime_decisions}

    assert request_index["req-unknown"].status == RequestStatus.DENY
    assert request_index["req-bad-region"].status == RequestStatus.DENY
    assert request_index["req-expired-a100"].status == RequestStatus.DENY
    assert request_index["req-high-cost-cpu"].status == RequestStatus.DENY

    assert runtime_index["runtime-unknown"].severity == Severity.CRITICAL
    assert runtime_index["runtime-bad-region"].severity == Severity.CRITICAL
    assert runtime_index["runtime-budget-exhausted"].severity == Severity.CRITICAL
    assert runtime_index["runtime-expired-a100"].severity == Severity.CRITICAL

    assert runtime_index["runtime-missing-activity"].severity == Severity.CRITICAL
    assert runtime_index["runtime-missing-activity"].idle_minutes == 120.0
    assert runtime_index["runtime-missing-activity"].stop_now is True


def test_edge_case_actions_emit_stop_and_notify_for_critical_resources():
    scenario = load_scenario(Path("data/scenario_edge_cases.json"))
    result = run_scenario(scenario)

    actions_by_resource: dict[str, set[str]] = {}
    for record in result.action_records:
        actions_by_resource.setdefault(record.resource_id, set()).add(record.action_type)

    assert ActionType.STOP_RUNTIME.value in actions_by_resource["runtime-unknown"]
    assert ActionType.NOTIFY.value in actions_by_resource["runtime-unknown"]

    assert ActionType.STOP_RUNTIME.value in actions_by_resource["runtime-budget-exhausted"]
    assert ActionType.NOTIFY.value in actions_by_resource["runtime-budget-exhausted"]


def test_repeat_critical_runtime_escalates_on_second_run():
    scenario = load_scenario(Path("data/scenario_student_a.json"))

    first_result, state = run_scenario_with_state(scenario)

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

    second_scenario = ScenarioInput(
        managed_project_ids=scenario.managed_project_ids,
        projects=scenario.projects,
        approvals=scenario.approvals,
        provisioning_requests=scenario.provisioning_requests,
        runtime_snapshots=tuple(later_snapshots),
    )

    second_result, _ = run_scenario_with_state(second_scenario, state)

    first_plan_index = {plan.resource_id: plan for plan in first_result.action_plans}
    second_plan_index = {plan.resource_id: plan for plan in second_result.action_plans}

    assert first_plan_index["runtime-001"].escalate_now is False
    assert second_plan_index["runtime-001"].escalate_now is True
    assert ActionType.ESCALATE in second_plan_index["runtime-001"].secondary_actions