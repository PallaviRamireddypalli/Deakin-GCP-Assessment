from __future__ import annotations

from dataclasses import dataclass

from .actions import ActionPlan, ActionType


@dataclass(frozen=True)
class ActionRecord:
    action_type: str
    project_id: str
    resource_id: str
    targets: tuple[str, ...]
    message: str


def execute_action_plans(plans: list[ActionPlan]) -> list[ActionRecord]:
    """
    Dry run executor.
    It does not talk to GCP.
    It only converts action plans into auditable action records.
    """
    records: list[ActionRecord] = []

    for plan in plans:
        if plan.primary_action == ActionType.NOOP:
            records.append(
                ActionRecord(
                    action_type=ActionType.NOOP.value,
                    project_id=plan.project_id,
                    resource_id=plan.resource_id,
                    targets=(),
                    message=plan.suppression_reason or "No action required.",
                )
            )
            continue

        if plan.stop_now:
            records.append(
                ActionRecord(
                    action_type=ActionType.STOP_RUNTIME.value,
                    project_id=plan.project_id,
                    resource_id=plan.resource_id,
                    targets=(),
                    message="Dry run: runtime would be stopped.",
                )
            )

        if plan.notify_now:
            records.append(
                ActionRecord(
                    action_type=ActionType.NOTIFY.value,
                    project_id=plan.project_id,
                    resource_id=plan.resource_id,
                    targets=plan.notify_targets,
                    message="Dry run: notification would be sent.",
                )
            )

        if plan.escalate_now:
            records.append(
                ActionRecord(
                    action_type=ActionType.ESCALATE.value,
                    project_id=plan.project_id,
                    resource_id=plan.resource_id,
                    targets=plan.notify_targets,
                    message="Dry run: incident would be escalated.",
                )
            )

    return records