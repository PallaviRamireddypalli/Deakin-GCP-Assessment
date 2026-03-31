from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .approvals import Approval
from .models import Decision, Project, ResourceStatus, RuntimeSnapshot, Severity
from .policy import assess_runtime_scope


@dataclass(frozen=True)
class DetectionConfig:
    allowed_regions: frozenset[str]
    allowed_machine_prefixes: tuple[str, ...] = ("n1", "n2", "e2")
    min_idle_minutes: int = 5
    max_idle_minutes: int = 20
    idle_budget_guardrail_ratio: float = 0.02
    reserve_budget_ratio: float = 0.25
    excessive_hourly_burn_ratio: float = 0.20


DEFAULT_CONFIG = DetectionConfig(
    allowed_regions=frozenset(
        {
            "us-west2-b",
            "us-west1-c",
            "australia-southeast2-locations",
            "us-west2-a",
            "australia-southeast2-b",
            "us-central1",
            "australia-southeast1-locations",
            "us-west1-a",
            "us-west1-locations",
            "australia-southeast2",
            "us-west1",
            "australia-southeast1-c",
            "us-central1-f",
            "us-central1-c",
            "australia-southeast2-c",
            "us-west2-locations",
            "us-central1-locations",
            "australia-southeast1-a",
            "us-central1-a",
            "us-west2-c",
            "australia-southeast2-a",
            "australia-southeast1-b",
            "us-west1-b",
            "australia-southeast1",
            "us-west2",
            "us-central1-b",
        }
    )
)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def minutes_between(earlier: datetime, later: datetime) -> float:
    return max(0.0, (later - earlier).total_seconds() / 60.0)


def compute_idle_minutes(snapshot: RuntimeSnapshot) -> float:
    baseline = snapshot.last_activity_at or snapshot.started_at
    return minutes_between(baseline, snapshot.observed_at)


def compute_adaptive_idle_threshold_minutes(
    project: Project,
    snapshot: RuntimeSnapshot,
    config: DetectionConfig,
) -> float:
    if snapshot.hourly_burn_rate_aud <= 0:
        return float(config.max_idle_minutes)

    allowed_idle_spend = max(
        project.budget_monthly_aud * config.idle_budget_guardrail_ratio,
        0.50,
    )
    raw_threshold = (allowed_idle_spend / snapshot.hourly_burn_rate_aud) * 60.0

    return clamp(
        raw_threshold,
        float(config.min_idle_minutes),
        float(config.max_idle_minutes),
    )


def evaluate_runtime(
    project: Project,
    snapshot: RuntimeSnapshot,
    config: DetectionConfig = DEFAULT_CONFIG,
    approvals: Iterable[Approval] = (),
) -> Decision:
    if not project.active or snapshot.status != ResourceStatus.RUNNING:
        return Decision(
            project_id=snapshot.project_id,
            resource_id=snapshot.resource_id,
            severity=Severity.OK,
            stop_now=False,
            notify=False,
            reasons=(),
            risk_score=0,
            idle_minutes=0.0,
            adaptive_idle_threshold_minutes=float(config.max_idle_minutes),
            notification_targets=project.principals,
        )

    reasons: list[str] = []
    risk_score = 0
    stop_now = False
    notify = False

    idle_minutes = compute_idle_minutes(snapshot)
    adaptive_idle_threshold = compute_adaptive_idle_threshold_minutes(
        project,
        snapshot,
        config,
    )

    remaining_budget = max(project.budget_monthly_aud - project.budget_spent_aud, 0.0)
    reserve_budget = project.budget_monthly_aud * config.reserve_budget_ratio
    predicted_spend_after_one_more_hour = (
        project.budget_spent_aud + snapshot.hourly_burn_rate_aud
    )

    scope = assess_runtime_scope(
        project,
        snapshot,
        approvals,
        observed_at=snapshot.observed_at,
        allowed_regions=config.allowed_regions,
        baseline_machine_prefixes=config.allowed_machine_prefixes,
        excessive_hourly_burn_ratio=config.excessive_hourly_burn_ratio,
    )

    excessive_burn = snapshot.hourly_burn_rate_aud >= (
        project.budget_monthly_aud * config.excessive_hourly_burn_ratio
    )
    idle_breach = idle_minutes >= adaptive_idle_threshold
    reserve_breach_next_hour = predicted_spend_after_one_more_hour > (
        project.budget_monthly_aud - reserve_budget
    )

    if not scope.allowed:
        reasons.extend(scope.reasons)
        risk_score += 40
        stop_now = True
        notify = True

    if excessive_burn:
        reasons.append(
            "Hourly burn rate is too high relative to the project's monthly budget."
        )
        risk_score += 20
        notify = True

    if idle_breach and snapshot.hourly_burn_rate_aud > 0:
        reasons.append(
            f"Runtime has been idle for {idle_minutes:.1f} minutes, exceeding the adaptive "
            f"threshold of {adaptive_idle_threshold:.1f} minutes."
        )
        risk_score += 30
        stop_now = True
        notify = True

    if reserve_breach_next_hour:
        reasons.append(
            "Allowing one more hour of runtime would consume the protected budget reserve."
        )
        risk_score += 20
        stop_now = True
        notify = True

    if remaining_budget <= 0:
        reasons.append("Project has no monthly budget remaining.")
        risk_score += 40
        stop_now = True
        notify = True

    if stop_now:
        severity = Severity.CRITICAL
    elif notify:
        severity = Severity.WARNING
    else:
        severity = Severity.OK

    return Decision(
        project_id=project.project_id,
        resource_id=snapshot.resource_id,
        severity=severity,
        stop_now=stop_now,
        notify=notify,
        reasons=tuple(reasons),
        risk_score=risk_score,
        idle_minutes=round(idle_minutes, 2),
        adaptive_idle_threshold_minutes=round(adaptive_idle_threshold, 2),
        notification_targets=project.principals,
    )


def evaluate_batch(
    projects: Iterable[Project],
    snapshots: Iterable[RuntimeSnapshot],
    config: DetectionConfig = DEFAULT_CONFIG,
    approvals: Iterable[Approval] = (),
) -> list[Decision]:
    project_index = {project.project_id: project for project in projects}
    decisions: list[Decision] = []

    for snapshot in snapshots:
        project = project_index.get(snapshot.project_id)

        if project is None:
            decisions.append(
                Decision(
                    project_id=snapshot.project_id,
                    resource_id=snapshot.resource_id,
                    severity=Severity.CRITICAL,
                    stop_now=True,
                    notify=True,
                    reasons=("Runtime belongs to an unknown or unmanaged project.",),
                    risk_score=50,
                    idle_minutes=0.0,
                    adaptive_idle_threshold_minutes=float(config.max_idle_minutes),
                    notification_targets=("platform-ops@example.edu",),
                )
            )
            continue

        decisions.append(
            evaluate_runtime(
                project,
                snapshot,
                config=config,
                approvals=approvals,
            )
        )

    return decisions