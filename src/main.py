from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .budgets import clone_project_with_resolved_budget
from .engine import evaluate_runtime
from .models import PrincipalMode, Project, ResourceStatus, RuntimeSnapshot, UseCase


def main() -> None:
    now = datetime(2026, 2, 22, 18, 0, tzinfo=UTC)

    student_project = Project(
        project_id="phd-student-a",
        name="Student A Colab Project",
        folder_path=("deakin.edu.au", "SEBE", "Eng", "PHD Research"),
        use_case=UseCase.PHD_RESEARCH,
        principal_mode=PrincipalMode.ONE_TO_ONE,
        principals=("student.a@deakin.edu.au",),
        budget_monthly_aud=150.0,
        budget_spent_aud=18.0,
        planned_products=("COLAB_ENTERPRISE",),
    )

    effective_project = clone_project_with_resolved_budget(student_project)

    runtime = RuntimeSnapshot(
        resource_id="runtime-001",
        project_id="phd-student-a",
        product="COLAB_ENTERPRISE",
        machine_type="a2-highgpu-1g",
        region="australia-southeast1",
        accelerator_type="A100",
        status=ResourceStatus.RUNNING,
        connected=True,
        observed_at=now,
        started_at=now - timedelta(hours=9),
        last_activity_at=now - timedelta(hours=9),
        hourly_burn_rate_aud=12.0,
    )

    decision = evaluate_runtime(effective_project, runtime)

    print("=== Decision ===")
    print(f"Severity: {decision.severity}")
    print(f"Stop now: {decision.stop_now}")
    print(f"Notify: {decision.notify}")
    print(f"Risk score: {decision.risk_score}")
    print(f"Idle minutes: {decision.idle_minutes}")
    print(f"Adaptive threshold: {decision.adaptive_idle_threshold_minutes}")
    print("Reasons:")
    for reason in decision.reasons:
        print(f" - {reason}")


if __name__ == "__main__":
    main()