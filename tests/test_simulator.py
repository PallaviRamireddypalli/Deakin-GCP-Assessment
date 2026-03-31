from __future__ import annotations

from pathlib import Path

from src.actions import ActionType
from src.approvals import RequestStatus
from src.models import Severity
from src.simulator import load_scenario, run_scenario


def test_simulator_end_to_end_student_a_scenario():
    scenario_path = Path("data/scenario_student_a.json")
    scenario = load_scenario(scenario_path)
    result = run_scenario(scenario)

    assert result.registry_sync.to_onboard == ("phd-student-a", "teaching-unit-01")
    assert result.registry_sync.to_offboard == ("legacy-project",)

    request_index = {item.request_id: item for item in result.request_decisions}

    assert request_index["req-student-a"].status == RequestStatus.DENY
    assert request_index["req-student-a"].allow is False

    assert request_index["req-teaching-a100"].status == RequestStatus.ALLOW_BY_EXCEPTION
    assert request_index["req-teaching-a100"].allow is True

    runtime_index = {item.resource_id: item for item in result.runtime_decisions}

    assert runtime_index["runtime-001"].severity == Severity.CRITICAL
    assert runtime_index["runtime-001"].stop_now is True
    assert runtime_index["runtime-001"].notify is True

    assert runtime_index["runtime-002"].severity in (Severity.OK, Severity.WARNING)

    action_types_for_runtime_001 = [
        record.action_type
        for record in result.action_records
        if record.resource_id == "runtime-001"
    ]

    assert ActionType.STOP_RUNTIME.value in action_types_for_runtime_001
    assert ActionType.NOTIFY.value in action_types_for_runtime_001