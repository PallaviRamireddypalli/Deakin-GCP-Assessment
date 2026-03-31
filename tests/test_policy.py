from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.approvals import Approval, ProvisioningRequest, RequestStatus
from src.engine import evaluate_runtime
from src.models import PrincipalMode, Project, ResourceStatus, RuntimeSnapshot, Severity, UseCase
from src.policy import evaluate_provisioning_request


def make_project(
    project_id: str,
    *,
    planned_products: tuple[str, ...] = ("COLAB_ENTERPRISE",),
    budget_monthly_aud: float = 150.0,
    budget_spent_aud: float = 0.0,
) -> Project:
    return Project(
        project_id=project_id,
        name=project_id,
        folder_path=("deakin.edu.au", "SEBE", "Eng", "PHD Research"),
        use_case=UseCase.PHD_RESEARCH,
        principal_mode=PrincipalMode.ONE_TO_ONE,
        principals=("owner@example.edu",),
        budget_monthly_aud=budget_monthly_aud,
        budget_spent_aud=budget_spent_aud,
        active=True,
        planned_products=planned_products,
    )


def make_request(
    project_id: str,
    *,
    request_id: str = "req-1",
    product: str = "COLAB_ENTERPRISE",
    machine_type: str = "n2-standard-4",
    region: str = "australia-southeast1",
    accelerator_type: str | None = None,
    estimated_hourly_burn_aud: float = 1.0,
    requested_at: datetime | None = None,
) -> ProvisioningRequest:
    requested_at = requested_at or datetime(2026, 2, 22, 18, 0, tzinfo=UTC)
    return ProvisioningRequest(
        request_id=request_id,
        project_id=project_id,
        product=product,
        machine_type=machine_type,
        region=region,
        requested_at=requested_at,
        requested_by="owner@example.edu",
        accelerator_type=accelerator_type,
        estimated_hourly_burn_aud=estimated_hourly_burn_aud,
    )


def make_approval(
    project_id: str,
    *,
    approval_id: str = "apr-1",
    products: tuple[str, ...] = ("COLAB_ENTERPRISE",),
    machine_prefixes: tuple[str, ...] = ("a2",),
    accelerators: tuple[str, ...] = ("A100",),
    approved_max_hourly_burn_aud: float | None = 20.0,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
) -> Approval:
    valid_from = valid_from or datetime(2026, 2, 1, 0, 0, tzinfo=UTC)
    valid_to = valid_to or datetime(2026, 3, 31, 23, 59, tzinfo=UTC)
    return Approval(
        approval_id=approval_id,
        project_id=project_id,
        valid_from=valid_from,
        valid_to=valid_to,
        approved_products=products,
        approved_machine_prefixes=machine_prefixes,
        approved_accelerators=accelerators,
        approved_max_hourly_burn_aud=approved_max_hourly_burn_aud,
        requested_by="owner@example.edu",
        approved_by="platform@example.edu",
        active=True,
    )


def make_snapshot(
    project_id: str,
    *,
    resource_id: str = "runtime-1",
    product: str = "COLAB_ENTERPRISE",
    machine_type: str = "n2-standard-4",
    region: str = "australia-southeast1",
    accelerator_type: str | None = None,
    hours_idle: float = 0.0,
    hourly_burn_rate_aud: float = 1.0,
) -> RuntimeSnapshot:
    now = datetime(2026, 2, 22, 18, 0, tzinfo=UTC)
    return RuntimeSnapshot(
        resource_id=resource_id,
        project_id=project_id,
        product=product,
        machine_type=machine_type,
        region=region,
        accelerator_type=accelerator_type,
        status=ResourceStatus.RUNNING,
        connected=True,
        observed_at=now,
        started_at=now - timedelta(hours=max(hours_idle, 1)),
        last_activity_at=now - timedelta(hours=hours_idle),
        hourly_burn_rate_aud=hourly_burn_rate_aud,
    )


def test_baseline_request_is_allowed():
    project = make_project("p1")
    request = make_request("p1", machine_type="n2-standard-4", estimated_hourly_burn_aud=1.0)

    decision = evaluate_provisioning_request(project, request, approvals=[])

    assert decision.allow is True
    assert decision.status == RequestStatus.ALLOW
    assert decision.notify is False


def test_unplanned_product_is_denied_without_approval():
    project = make_project("p1", planned_products=("BIGQUERY",))
    request = make_request("p1", product="COLAB_ENTERPRISE")

    decision = evaluate_provisioning_request(project, request, approvals=[])

    assert decision.allow is False
    assert decision.status == RequestStatus.DENY
    assert decision.notify is True
    assert any("planned products" in reason.lower() for reason in decision.reasons)


def test_high_cost_cpu_request_is_denied_without_approval():
    project = make_project("p1", planned_products=("COLAB_ENTERPRISE",), budget_monthly_aud=150.0)
    request = make_request(
        "p1",
        machine_type="n2-highmem-128",
        estimated_hourly_burn_aud=40.0,
    )

    decision = evaluate_provisioning_request(project, request, approvals=[])

    assert decision.allow is False
    assert decision.status == RequestStatus.DENY
    assert any("estimated hourly burn" in reason.lower() for reason in decision.reasons)


def test_approved_exception_allows_a100_request():
    project = make_project("p1")
    request = make_request(
        "p1",
        machine_type="a2-highgpu-1g",
        accelerator_type="A100",
        estimated_hourly_burn_aud=12.0,
    )
    approval = make_approval("p1")

    decision = evaluate_provisioning_request(project, request, approvals=[approval])

    assert decision.allow is True
    assert decision.status == RequestStatus.ALLOW_BY_EXCEPTION
    assert decision.matched_approval_id == "apr-1"


def test_wrong_project_cannot_use_other_projects_approval():
    project = make_project("p2")
    request = make_request(
        "p2",
        machine_type="a2-highgpu-1g",
        accelerator_type="A100",
        estimated_hourly_burn_aud=12.0,
    )
    approval = make_approval("p1")

    decision = evaluate_provisioning_request(project, request, approvals=[approval])

    assert decision.allow is False
    assert decision.status == RequestStatus.DENY


def test_expired_approval_does_not_allow_request():
    project = make_project("p1")
    request = make_request(
        "p1",
        machine_type="a2-highgpu-1g",
        accelerator_type="A100",
        estimated_hourly_burn_aud=12.0,
    )
    expired_approval = make_approval(
        "p1",
        valid_from=datetime(2025, 1, 1, 0, 0, tzinfo=UTC),
        valid_to=datetime(2025, 1, 31, 23, 59, tzinfo=UTC),
    )

    decision = evaluate_provisioning_request(project, request, approvals=[expired_approval])

    assert decision.allow is False
    assert decision.status == RequestStatus.DENY


def test_runtime_with_approved_exception_and_recent_activity_is_ok():
    project = make_project("p1", budget_monthly_aud=150.0, budget_spent_aud=10.0)
    approval = make_approval("p1")
    snapshot = make_snapshot(
        "p1",
        machine_type="a2-highgpu-1g",
        accelerator_type="A100",
        hours_idle=0.02,
        hourly_burn_rate_aud=12.0,
    )

    decision = evaluate_runtime(project, snapshot, approvals=[approval])

    assert decision.severity in (Severity.OK, Severity.WARNING)
    assert all("machine type" not in reason.lower() for reason in decision.reasons)


def test_runtime_with_approved_exception_can_still_be_stopped_for_idle_budget_risk():
    project = make_project("p1", budget_monthly_aud=150.0, budget_spent_aud=18.0)
    approval = make_approval("p1")
    snapshot = make_snapshot(
        "p1",
        machine_type="a2-highgpu-1g",
        accelerator_type="A100",
        hours_idle=9.0,
        hourly_burn_rate_aud=12.0,
    )

    decision = evaluate_runtime(project, snapshot, approvals=[approval])

    assert decision.severity == Severity.CRITICAL
    assert decision.stop_now is True
    assert any("idle" in reason.lower() for reason in decision.reasons)
    assert all("machine type" not in reason.lower() for reason in decision.reasons)