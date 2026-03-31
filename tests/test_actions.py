from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.actions import ActionType, apply_action_plan, build_action_plan
from src.models import Decision, Severity
from src.state import EngineState, get_resource_state


def make_decision(
    *,
    severity: Severity = Severity.CRITICAL,
    stop_now: bool = True,
    notify: bool = True,
    project_id: str = "p1",
    resource_id: str = "r1",
) -> Decision:
    return Decision(
        project_id=project_id,
        resource_id=resource_id,
        severity=severity,
        stop_now=stop_now,
        notify=notify,
        reasons=("test reason",),
        risk_score=70,
        idle_minutes=60.0,
        adaptive_idle_threshold_minutes=15.0,
        notification_targets=("owner@example.edu",),
    )


def test_first_critical_decision_stops_and_notifies():
    state = EngineState()
    observed_at = datetime(2026, 2, 22, 18, 0, tzinfo=UTC)
    decision = make_decision()

    plan = build_action_plan(decision, state, observed_at)

    assert plan.primary_action == ActionType.STOP_RUNTIME
    assert plan.notify_now is True
    assert plan.stop_now is True
    assert plan.escalate_now is False


def test_repeat_decision_within_cooldown_suppresses_notification():
    state = EngineState()
    first_seen = datetime(2026, 2, 22, 18, 0, tzinfo=UTC)
    decision = make_decision()

    first_plan = build_action_plan(decision, state, first_seen)
    apply_action_plan(state, first_plan, first_seen, decision.severity)

    second_seen = first_seen + timedelta(minutes=10)
    second_plan = build_action_plan(decision, state, second_seen)

    assert second_plan.stop_now is True
    assert second_plan.notify_now is False
    assert second_plan.suppression_reason is not None


def test_repeat_critical_stop_after_prior_stop_escalates():
    state = EngineState()
    first_seen = datetime(2026, 2, 22, 18, 0, tzinfo=UTC)
    decision = make_decision()

    first_plan = build_action_plan(decision, state, first_seen)
    apply_action_plan(state, first_plan, first_seen, decision.severity)

    second_seen = first_seen + timedelta(minutes=45)
    second_plan = build_action_plan(decision, state, second_seen)

    assert second_plan.primary_action == ActionType.STOP_RUNTIME
    assert second_plan.notify_now is True
    assert second_plan.escalate_now is True
    assert ActionType.ESCALATE in second_plan.secondary_actions


def test_warning_decision_notifies_without_stop():
    state = EngineState()
    observed_at = datetime(2026, 2, 22, 18, 0, tzinfo=UTC)
    decision = make_decision(severity=Severity.WARNING, stop_now=False, notify=True)

    plan = build_action_plan(decision, state, observed_at)

    assert plan.primary_action == ActionType.NOTIFY
    assert plan.stop_now is False
    assert plan.notify_now is True


def test_apply_action_plan_persists_state():
    state = EngineState()
    observed_at = datetime(2026, 2, 22, 18, 0, tzinfo=UTC)
    decision = make_decision()

    plan = build_action_plan(decision, state, observed_at)
    apply_action_plan(state, plan, observed_at, decision.severity)

    saved = get_resource_state(state, decision.project_id, decision.resource_id)

    assert saved.last_seen_at == observed_at
    assert saved.last_stop_at == observed_at
    assert saved.last_notification_at == observed_at
    assert saved.last_decision_severity == Severity.CRITICAL