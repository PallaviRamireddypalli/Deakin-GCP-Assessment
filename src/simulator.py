from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .actions import ActionPlan, apply_action_plan, build_action_plans
from .approvals import Approval
from .approvals import ProvisioningRequest
from .approvals import RequestDecision
from .approvals import RequestStatus
from .budgets import clone_projects_with_resolved_budgets
from .engine import Decision
from .engine import evaluate_batch
from .executor import ActionRecord
from .executor import execute_action_plans
from .models import PrincipalMode
from .models import Project
from .models import ResourceStatus
from .models import RuntimeSnapshot
from .models import UseCase
from .policy import evaluate_provisioning_request
from .registry import RegistrySyncResult
from .registry import sync_managed_projects
from .state import EngineState


@dataclass(frozen=True)
class ScenarioInput:
    managed_project_ids: tuple[str, ...]
    projects: tuple[Project, ...]
    approvals: tuple[Approval, ...]
    provisioning_requests: tuple[ProvisioningRequest, ...]
    runtime_snapshots: tuple[RuntimeSnapshot, ...]


@dataclass(frozen=True)
class SimulationResult:
    registry_sync: RegistrySyncResult
    request_decisions: tuple[RequestDecision, ...]
    runtime_decisions: tuple[Decision, ...]
    action_plans: tuple[ActionPlan, ...]
    action_records: tuple[ActionRecord, ...]


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_use_case(value: str) -> UseCase:
    return UseCase(value)


def _parse_principal_mode(value: str) -> PrincipalMode:
    return PrincipalMode(value)


def _parse_status(value: str | None) -> ResourceStatus:
    if value is None:
        return ResourceStatus.RUNNING
    return ResourceStatus(value)


def parse_project(item: dict[str, Any]) -> Project:
    return Project(
        project_id=item["project_id"],
        name=item["name"],
        folder_path=tuple(item["folder_path"]),
        use_case=_parse_use_case(item["use_case"]),
        principal_mode=_parse_principal_mode(item["principal_mode"]),
        principals=tuple(item["principals"]),
        budget_monthly_aud=float(item.get("budget_monthly_aud", 0.0)),
        budget_spent_aud=float(item.get("budget_spent_aud", 0.0)),
        active=bool(item.get("active", True)),
        planned_products=tuple(item.get("planned_products", ())),
        labels=dict(item.get("labels", {})),
    )


def parse_approval(item: dict[str, Any]) -> Approval:
    approved_max_hourly_burn_aud = item.get("approved_max_hourly_burn_aud")
    if approved_max_hourly_burn_aud is not None:
        approved_max_hourly_burn_aud = float(approved_max_hourly_burn_aud)

    return Approval(
        approval_id=item["approval_id"],
        project_id=item["project_id"],
        valid_from=_parse_datetime(item["valid_from"]),
        valid_to=_parse_datetime(item["valid_to"]),
        approved_products=tuple(item.get("approved_products", ())),
        approved_machine_prefixes=tuple(item.get("approved_machine_prefixes", ())),
        approved_accelerators=tuple(item.get("approved_accelerators", ())),
        approved_max_hourly_burn_aud=approved_max_hourly_burn_aud,
        requested_by=item.get("requested_by", ""),
        approved_by=item.get("approved_by", ""),
        active=bool(item.get("active", True)),
    )


def parse_request(item: dict[str, Any]) -> ProvisioningRequest:
    return ProvisioningRequest(
        request_id=item["request_id"],
        project_id=item["project_id"],
        product=item["product"],
        machine_type=item["machine_type"],
        region=item["region"],
        requested_at=_parse_datetime(item["requested_at"]),
        requested_by=item["requested_by"],
        estimated_hourly_burn_aud=float(item["estimated_hourly_burn_aud"]),
        accelerator_type=item.get("accelerator_type"),
    )


def parse_snapshot(item: dict[str, Any]) -> RuntimeSnapshot:
    last_activity_at_raw = item.get("last_activity_at")
    last_activity_at = None
    if last_activity_at_raw is not None:
        last_activity_at = _parse_datetime(last_activity_at_raw)

    return RuntimeSnapshot(
        resource_id=item["resource_id"],
        project_id=item["project_id"],
        product=item["product"],
        machine_type=item["machine_type"],
        region=item["region"],
        accelerator_type=item.get("accelerator_type"),
        status=_parse_status(item.get("status")),
        connected=bool(item.get("connected", True)),
        observed_at=_parse_datetime(item["observed_at"]),
        started_at=_parse_datetime(item["started_at"]),
        last_activity_at=last_activity_at,
        hourly_burn_rate_aud=float(item["hourly_burn_rate_aud"]),
    )


def load_scenario(path: str | Path) -> ScenarioInput:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))

    return ScenarioInput(
        managed_project_ids=tuple(raw.get("managed_project_ids", [])),
        projects=tuple(parse_project(item) for item in raw.get("projects", [])),
        approvals=tuple(parse_approval(item) for item in raw.get("approvals", [])),
        provisioning_requests=tuple(
            parse_request(item) for item in raw.get("provisioning_requests", [])
        ),
        runtime_snapshots=tuple(
            parse_snapshot(item) for item in raw.get("runtime_snapshots", [])
        ),
    )


def _serialize(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()

    if isinstance(obj, tuple):
        return [_serialize(item) for item in obj]

    if isinstance(obj, list):
        return [_serialize(item) for item in obj]

    if isinstance(obj, dict):
        return {key: _serialize(value) for key, value in obj.items()}

    if hasattr(obj, "value"):
        return obj.value

    if hasattr(obj, "__dataclass_fields__"):
        return _serialize(asdict(obj))

    return obj


def run_scenario_with_state(
    scenario: ScenarioInput,
    state: EngineState | None = None,
) -> tuple[SimulationResult, EngineState]:
    working_state = state if state is not None else EngineState()

    effective_projects = clone_projects_with_resolved_budgets(list(scenario.projects))
    project_index = {project.project_id: project for project in effective_projects}

    registry_sync = sync_managed_projects(
        discovered_projects=effective_projects,
        currently_managed_project_ids=set(scenario.managed_project_ids),
    )

    request_decisions: list[RequestDecision] = []
    for request in scenario.provisioning_requests:
        project = project_index.get(request.project_id)

        if project is None:
            request_decisions.append(
                RequestDecision(
                    project_id=request.project_id,
                    request_id=request.request_id,
                    status=RequestStatus.DENY,
                    allow=False,
                    notify=True,
                    reasons=("Provisioning request belongs to an unknown project.",),
                    matched_approval_id=None,
                )
            )
            continue

        request_decisions.append(
            evaluate_provisioning_request(
                project=project,
                request=request,
                approvals=scenario.approvals,
            )
        )

    runtime_decisions = evaluate_batch(
        projects=effective_projects,
        snapshots=scenario.runtime_snapshots,
        approvals=scenario.approvals,
    )

    action_plans: list[ActionPlan] = []
    for snapshot, decision in zip(scenario.runtime_snapshots, runtime_decisions):
        plan = build_action_plans(
            decisions=[decision],
            state=working_state,
            observed_at=snapshot.observed_at,
        )[0]

        action_plans.append(plan)
        apply_action_plan(working_state, plan, snapshot.observed_at, decision.severity)

    action_records = execute_action_plans(action_plans)

    result = SimulationResult(
        registry_sync=registry_sync,
        request_decisions=tuple(request_decisions),
        runtime_decisions=tuple(runtime_decisions),
        action_plans=tuple(action_plans),
        action_records=tuple(action_records),
    )

    return result, working_state


def run_scenario(scenario: ScenarioInput) -> SimulationResult:
    result, _ = run_scenario_with_state(scenario)
    return result


def simulation_result_to_json(result: SimulationResult) -> str:
    return json.dumps(_serialize(result), indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local GCP guardrail scenario.")
    parser.add_argument("scenario_path", help="Path to the scenario JSON file.")
    args = parser.parse_args()

    scenario = load_scenario(args.scenario_path)
    result = run_scenario(scenario)
    print(simulation_result_to_json(result))


if __name__ == "__main__":
    main()