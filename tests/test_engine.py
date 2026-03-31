from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.engine import evaluate_batch, evaluate_runtime
from src.models import PrincipalMode, Project, ResourceStatus, RuntimeSnapshot, Severity, UseCase
from src.registry import FolderNode, discover_projects, sync_managed_projects


def make_project(
    project_id: str,
    *,
    budget_monthly_aud: float = 150.0,
    budget_spent_aud: float = 0.0,
    active: bool = True,
    principal_mode: PrincipalMode = PrincipalMode.ONE_TO_ONE,
    principals: tuple[str, ...] = ("owner@example.edu",),
    use_case: UseCase = UseCase.PHD_RESEARCH,
) -> Project:
    return Project(
        project_id=project_id,
        name=project_id,
        folder_path=("deakin.edu.au", "SEBE", "Eng", "PHD Research"),
        use_case=use_case,
        principal_mode=principal_mode,
        principals=principals,
        budget_monthly_aud=budget_monthly_aud,
        budget_spent_aud=budget_spent_aud,
        active=active,
        planned_products=("COLAB_ENTERPRISE",),
    )


def make_snapshot(
    project_id: str,
    *,
    resource_id: str = "runtime-1",
    machine_type: str = "n2-standard-4",
    region: str = "australia-southeast1",
    hours_idle: float = 0.0,
    hourly_burn_rate_aud: float = 1.0,
) -> RuntimeSnapshot:
    now = datetime(2026, 2, 22, 18, 0, tzinfo=UTC)
    return RuntimeSnapshot(
        resource_id=resource_id,
        project_id=project_id,
        product="COLAB_ENTERPRISE",
        machine_type=machine_type,
        region=region,
        accelerator_type=None,
        status=ResourceStatus.RUNNING,
        connected=True,
        observed_at=now,
        started_at=now - timedelta(hours=max(hours_idle, 1)),
        last_activity_at=now - timedelta(hours=hours_idle),
        hourly_burn_rate_aud=hourly_burn_rate_aud,
    )


def test_recursive_discovery_has_no_blind_spots():
    p1 = make_project("p1", use_case=UseCase.PHD_RESEARCH)
    p2 = make_project("p2", use_case=UseCase.TEACHING_AND_LEARNING)
    p3 = make_project("p3", use_case=UseCase.PROFESSIONAL_STAFF)

    root = FolderNode(
        name="deakin.edu.au",
        children=[
            FolderNode(
                name="SEBE",
                children=[
                    FolderNode(
                        name="Eng",
                        children=[
                            FolderNode(name="PHD Research", projects=[p1]),
                        ],
                    ),
                    FolderNode(
                        name="SIT",
                        children=[
                            FolderNode(name="Units", projects=[p2]),
                        ],
                    ),
                ],
            ),
            FolderNode(
                name="Digital Services",
                projects=[p3],
            ),
        ],
    )

    discovered = discover_projects(root)
    discovered_ids = {project.project_id for project in discovered}

    assert discovered_ids == {"p1", "p2", "p3"}


def test_registry_sync_onboards_and_offboards_automatically():
    discovered = [
        make_project("p1"),
        make_project("p2"),
        make_project("p3"),
    ]
    currently_managed = {"p2", "old-project"}

    result = sync_managed_projects(discovered, currently_managed)

    assert result.to_onboard == ("p1", "p3")
    assert result.to_offboard == ("old-project",)
    assert result.unchanged == ("p2",)


def test_student_a_style_idle_expensive_runtime_is_stopped():
    project = make_project("student-a", budget_monthly_aud=150.0, budget_spent_aud=18.0)
    snapshot = make_snapshot(
        "student-a",
        machine_type="a2-highgpu-1g",
        hours_idle=9.0,
        hourly_burn_rate_aud=12.0,
    )

    decision = evaluate_runtime(project, snapshot)

    assert decision.severity == Severity.CRITICAL
    assert decision.stop_now is True
    assert decision.notify is True
    assert any("idle" in reason.lower() for reason in decision.reasons)
    assert any("machine type" in reason.lower() for reason in decision.reasons)


def test_recently_active_runtime_is_not_stopped():
    project = make_project("student-b", budget_monthly_aud=150.0, budget_spent_aud=10.0)
    snapshot = make_snapshot(
        "student-b",
        machine_type="n2-standard-4",
        hours_idle=0.05,  # 3 minutes
        hourly_burn_rate_aud=0.50,
    )

    decision = evaluate_runtime(project, snapshot)

    assert decision.severity == Severity.OK
    assert decision.stop_now is False
    assert decision.notify is False


def test_disallowed_machine_type_is_stopped_even_if_not_idle():
    project = make_project("student-c")
    snapshot = make_snapshot(
        "student-c",
        machine_type="a2-highgpu-1g",
        hours_idle=0.01,
        hourly_burn_rate_aud=12.0,
    )

    decision = evaluate_runtime(project, snapshot)

    assert decision.severity == Severity.CRITICAL
    assert decision.stop_now is True
    assert any("machine type" in reason.lower() for reason in decision.reasons)


def test_unknown_project_is_treated_as_critical_blind_spot():
    snapshots = [
        make_snapshot(
            "unknown-project",
            machine_type="n2-standard-4",
            hours_idle=2.0,
            hourly_burn_rate_aud=2.0,
        )
    ]

    decisions = evaluate_batch(projects=[], snapshots=snapshots)
    decision = decisions[0]

    assert decision.severity == Severity.CRITICAL
    assert decision.stop_now is True
    assert decision.notify is True
    assert "unknown or unmanaged project" in decision.reasons[0].lower()


def test_one_to_many_principals_are_all_notified():
    project = make_project(
        "shared-project",
        principal_mode=PrincipalMode.ONE_TO_MANY,
        principals=("student@example.edu", "supervisor@example.edu"),
    )
    snapshot = make_snapshot(
        "shared-project",
        machine_type="a2-highgpu-1g",
        hours_idle=2.0,
        hourly_burn_rate_aud=10.0,
    )

    decision = evaluate_runtime(project, snapshot)

    assert decision.notify is True
    assert decision.notification_targets == (
        "student@example.edu",
        "supervisor@example.edu",
    )


def test_engine_handles_1600_projects_in_one_batch():
    projects = [make_project(f"p{i}") for i in range(1600)]
    snapshots = [
        make_snapshot(
            f"p{i}",
            machine_type="n2-standard-4",
            hours_idle=0.01,
            hourly_burn_rate_aud=0.10,
            resource_id=f"r{i}",
        )
        for i in range(1600)
    ]

    decisions = evaluate_batch(projects, snapshots)

    assert len(decisions) == 1600
    assert all(decision.severity == Severity.OK for decision in decisions)