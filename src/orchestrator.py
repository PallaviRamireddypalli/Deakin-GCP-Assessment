from __future__ import annotations

from dataclasses import dataclass

from .actions import ActionPlan
from .actions import apply_action_plan
from .actions import build_action_plans
from .approvals import RequestDecision
from .approvals import RequestStatus
from .budgets import clone_projects_with_resolved_budgets
from .engine import Decision
from .engine import evaluate_batch
from .executor import ActionRecord
from .executor import execute_action_plans
from .policy import evaluate_provisioning_request
from .ports import ApprovalRepositoryPort
from .ports import ManagedProjectRegistryPort
from .ports import NotificationMessage
from .ports import NotifierPort
from .ports import ProjectDiscoveryPort
from .ports import ProvisioningRequestRepositoryPort
from .ports import RuntimeControllerPort
from .ports import RuntimeInventoryPort
from .ports import StateStorePort
from .registry import RegistrySyncResult
from .registry import sync_managed_projects


@dataclass(frozen=True)
class AdapterConfig:
    notify_denied_requests: bool = True


@dataclass(frozen=True)
class OrchestrationResult:
    registry_sync: RegistrySyncResult
    request_decisions: tuple[RequestDecision, ...]
    runtime_decisions: tuple[Decision, ...]
    action_plans: tuple[ActionPlan, ...]
    action_records: tuple[ActionRecord, ...]


def _dedupe_targets(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []

    for value in values:
        item = value.strip()
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)

    return tuple(ordered)


def _build_request_notification(
    request_id: str,
    targets: tuple[str, ...],
    reasons: tuple[str, ...],
) -> NotificationMessage:
    body = "\n".join(reasons) if reasons else "Provisioning request was denied."

    return NotificationMessage(
        category="REQUEST_DENIED",
        subject=f"Provisioning denied: {request_id}",
        body=body,
        targets=targets,
    )


def _build_runtime_notification(
    resource_id: str,
    targets: tuple[str, ...],
    reasons: tuple[str, ...],
) -> NotificationMessage:
    body = "\n".join(reasons) if reasons else "Runtime requires attention."

    return NotificationMessage(
        category="RUNTIME_ALERT",
        subject=f"Runtime action required: {resource_id}",
        body=body,
        targets=targets,
    )


def _build_escalation_notification(
    resource_id: str,
    targets: tuple[str, ...],
    reasons: tuple[str, ...],
) -> NotificationMessage:
    body = "\n".join(reasons) if reasons else "Repeated critical runtime incident."

    return NotificationMessage(
        category="RUNTIME_ESCALATION",
        subject=f"Runtime escalation: {resource_id}",
        body=body,
        targets=targets,
    )


def orchestrate_cycle(
    *,
    project_discovery: ProjectDiscoveryPort,
    approval_repository: ApprovalRepositoryPort,
    request_repository: ProvisioningRequestRepositoryPort,
    runtime_inventory: RuntimeInventoryPort,
    runtime_controller: RuntimeControllerPort,
    notifier: NotifierPort,
    state_store: StateStorePort,
    managed_project_registry: ManagedProjectRegistryPort,
    config: AdapterConfig = AdapterConfig(),
) -> OrchestrationResult:
    discovered_projects = project_discovery.discover_projects()
    effective_projects = clone_projects_with_resolved_budgets(discovered_projects)
    project_index = {project.project_id: project for project in effective_projects}

    current_managed_ids = managed_project_registry.load_managed_project_ids()
    registry_sync = sync_managed_projects(
        discovered_projects=effective_projects,
        currently_managed_project_ids=current_managed_ids,
    )

    managed_project_registry.replace_managed_project_ids(
        {project.project_id for project in effective_projects if project.active}
    )

    approvals = approval_repository.list_approvals()

    request_decisions: list[RequestDecision] = []
    for request in request_repository.list_requests():
        project = project_index.get(request.project_id)

        if project is None:
            decision = RequestDecision(
                project_id=request.project_id,
                request_id=request.request_id,
                status=RequestStatus.DENY,
                allow=False,
                notify=True,
                reasons=("Provisioning request belongs to an unknown project.",),
                matched_approval_id=None,
            )
        else:
            decision = evaluate_provisioning_request(
                project=project,
                request=request,
                approvals=approvals,
            )

        request_decisions.append(decision)

        if config.notify_denied_requests and decision.status == RequestStatus.DENY:
            targets = _dedupe_targets(
                [request.requested_by]
                + list(project_index.get(request.project_id).principals if request.project_id in project_index else ())
            )
            notifier.notify(
                _build_request_notification(
                    request_id=request.request_id,
                    targets=targets,
                    reasons=decision.reasons,
                )
            )

    runtime_snapshots = runtime_inventory.list_runtime_snapshots()
    runtime_decisions = evaluate_batch(
        projects=effective_projects,
        snapshots=runtime_snapshots,
        approvals=approvals,
    )

    state = state_store.load_state()
    action_plans: list[ActionPlan] = []

    for snapshot, decision in zip(runtime_snapshots, runtime_decisions):
        plan = build_action_plans(
            decisions=[decision],
            state=state,
            observed_at=snapshot.observed_at,
        )[0]
        action_plans.append(plan)

        if plan.stop_now:
            runtime_controller.stop_runtime(
                project_id=plan.project_id,
                resource_id=plan.resource_id,
                reasons=plan.rationale,
            )

        if plan.notify_now:
            notifier.notify(
                _build_runtime_notification(
                    resource_id=plan.resource_id,
                    targets=plan.notify_targets,
                    reasons=plan.rationale,
                )
            )

        if plan.escalate_now:
            notifier.escalate(
                _build_escalation_notification(
                    resource_id=plan.resource_id,
                    targets=plan.notify_targets,
                    reasons=plan.rationale,
                )
            )

        apply_action_plan(state, plan, snapshot.observed_at, decision.severity)

    state_store.save_state(state)

    action_records = execute_action_plans(action_plans)

    return OrchestrationResult(
        registry_sync=registry_sync,
        request_decisions=tuple(request_decisions),
        runtime_decisions=tuple(runtime_decisions),
        action_plans=tuple(action_plans),
        action_records=tuple(action_records),
    )