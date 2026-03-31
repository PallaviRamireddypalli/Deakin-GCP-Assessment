from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Iterable, Optional

from .models import Decision, Severity
from .state import EngineState, ResourceState, get_resource_state, save_resource_state


class ActionType(StrEnum):
    NOOP = "NOOP"
    NOTIFY = "NOTIFY"
    STOP_RUNTIME = "STOP_RUNTIME"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True)
class PlannerConfig:
    notification_cooldown_minutes: int = 30


@dataclass(frozen=True)
class ActionPlan:
    project_id: str
    resource_id: str
    primary_action: ActionType
    secondary_actions: tuple[ActionType, ...]
    notify_targets: tuple[str, ...]
    notify_now: bool
    stop_now: bool
    escalate_now: bool
    suppression_reason: Optional[str]
    rationale: tuple[str, ...]
    risk_score: int


def _minutes_between(earlier: datetime, later: datetime) -> float:
    return max(0.0, (later - earlier).total_seconds() / 60.0)


def _notification_allowed(
    resource_state: ResourceState,
    observed_at: datetime,
    config: PlannerConfig,
) -> tuple[bool, Optional[str]]:
    if resource_state.last_notification_at is None:
        return True, None

    elapsed_minutes = _minutes_between(resource_state.last_notification_at, observed_at)
    if elapsed_minutes >= config.notification_cooldown_minutes:
        return True, None

    remaining_minutes = config.notification_cooldown_minutes - elapsed_minutes
    return (
        False,
        f"Notification cooldown active for another {remaining_minutes:.1f} minutes.",
    )


def build_action_plan(
    decision: Decision,
    state: EngineState,
    observed_at: datetime,
    config: PlannerConfig = PlannerConfig(),
) -> ActionPlan:
    resource_state = get_resource_state(state, decision.project_id, decision.resource_id)
    notify_allowed, suppression_reason = _notification_allowed(
        resource_state,
        observed_at,
        config,
    )

    stop_now = decision.stop_now
    notify_now = decision.notify and notify_allowed
    escalate_now = (
        decision.severity == Severity.CRITICAL
        and stop_now
        and resource_state.last_stop_at is not None
    )

    primary_action = ActionType.NOOP
    secondary_actions: list[ActionType] = []

    if stop_now:
        primary_action = ActionType.STOP_RUNTIME
        if notify_now:
            secondary_actions.append(ActionType.NOTIFY)
        if escalate_now:
            secondary_actions.append(ActionType.ESCALATE)
    elif notify_now:
        primary_action = ActionType.NOTIFY
    elif decision.severity == Severity.CRITICAL and suppression_reason is not None:
        primary_action = ActionType.NOOP

    return ActionPlan(
        project_id=decision.project_id,
        resource_id=decision.resource_id,
        primary_action=primary_action,
        secondary_actions=tuple(secondary_actions),
        notify_targets=decision.notification_targets if notify_now else (),
        notify_now=notify_now,
        stop_now=stop_now,
        escalate_now=escalate_now,
        suppression_reason=None if notify_now else suppression_reason,
        rationale=decision.reasons,
        risk_score=decision.risk_score,
    )


def build_action_plans(
    decisions: Iterable[Decision],
    state: EngineState,
    observed_at: datetime,
    config: PlannerConfig = PlannerConfig(),
) -> list[ActionPlan]:
    return [
        build_action_plan(decision, state, observed_at, config)
        for decision in decisions
    ]


def apply_action_plan(
    state: EngineState,
    plan: ActionPlan,
    observed_at: datetime,
    severity: Severity,
) -> None:
    existing = get_resource_state(state, plan.project_id, plan.resource_id)

    updated = ResourceState(
        last_notification_at=(
            observed_at if plan.notify_now else existing.last_notification_at
        ),
        last_stop_at=observed_at if plan.stop_now else existing.last_stop_at,
        last_seen_at=observed_at,
        last_decision_severity=severity,
    )

    save_resource_state(state, plan.project_id, plan.resource_id, updated)