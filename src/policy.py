from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from .approvals import (
    Approval,
    ProvisioningRequest,
    RequestDecision,
    RequestStatus,
    accelerator_in_list,
    approval_is_active,
    product_in_list,
)
from .models import Project, RuntimeSnapshot


DEFAULT_ALLOWED_REGIONS = frozenset(
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

DEFAULT_BASELINE_MACHINE_PREFIXES = ("n1", "n2", "e2")
DEFAULT_EXCESSIVE_HOURLY_BURN_RATIO = 0.20


@dataclass(frozen=True)
class RuntimeScopeDecision:
    allowed: bool
    allowed_by_exception: bool
    reasons: tuple[str, ...]
    matched_approval_id: Optional[str]


def machine_prefix_matches(machine_type: str, allowed_prefixes: tuple[str, ...]) -> bool:
    candidate = machine_type.strip().lower()
    return any(candidate.startswith(prefix.lower()) for prefix in allowed_prefixes)


def product_in_project_plan(project: Project, product: str) -> bool:
    return product_in_list(product, project.planned_products)


def hourly_burn_is_excessive(
    project: Project,
    hourly_burn_aud: float,
    excessive_hourly_burn_ratio: float = DEFAULT_EXCESSIVE_HOURLY_BURN_RATIO,
) -> bool:
    return hourly_burn_aud >= (project.budget_monthly_aud * excessive_hourly_burn_ratio)


def approval_matches_scope(
    approval: Approval,
    *,
    project_id: str,
    product: str,
    machine_type: str,
    accelerator_type: Optional[str],
    when: datetime,
    hourly_burn_aud: float,
) -> bool:
    if approval.project_id != project_id:
        return False

    if not approval_is_active(approval, when):
        return False

    if not product_in_list(product, approval.approved_products):
        return False

    if approval.approved_machine_prefixes:
        if not machine_prefix_matches(machine_type, approval.approved_machine_prefixes):
            return False

    if accelerator_type is not None:
        if not approval.approved_accelerators:
            return False
        if not accelerator_in_list(accelerator_type, approval.approved_accelerators):
            return False

    if approval.approved_max_hourly_burn_aud is not None:
        if hourly_burn_aud > approval.approved_max_hourly_burn_aud:
            return False

    return True


def find_matching_approval(
    approvals: Iterable[Approval],
    *,
    project_id: str,
    product: str,
    machine_type: str,
    accelerator_type: Optional[str],
    when: datetime,
    hourly_burn_aud: float,
) -> Optional[Approval]:
    for approval in approvals:
        if approval_matches_scope(
            approval,
            project_id=project_id,
            product=product,
            machine_type=machine_type,
            accelerator_type=accelerator_type,
            when=when,
            hourly_burn_aud=hourly_burn_aud,
        ):
            return approval
    return None


def evaluate_provisioning_request(
    project: Project,
    request: ProvisioningRequest,
    approvals: Iterable[Approval],
    *,
    allowed_regions: frozenset[str] = DEFAULT_ALLOWED_REGIONS,
    baseline_machine_prefixes: tuple[str, ...] = DEFAULT_BASELINE_MACHINE_PREFIXES,
    excessive_hourly_burn_ratio: float = DEFAULT_EXCESSIVE_HOURLY_BURN_RATIO,
) -> RequestDecision:
    reasons: list[str] = []

    if request.region not in allowed_regions:
        reasons.append(f"Region '{request.region}' is not in allowed locations.")
        return RequestDecision(
            project_id=project.project_id,
            request_id=request.request_id,
            status=RequestStatus.DENY,
            allow=False,
            notify=True,
            reasons=tuple(reasons),
            matched_approval_id=None,
        )

    product_allowed_by_plan = product_in_project_plan(project, request.product)
    machine_allowed_by_baseline = machine_prefix_matches(
        request.machine_type,
        baseline_machine_prefixes,
    )
    accelerator_requested = request.accelerator_type is not None
    burn_excessive = hourly_burn_is_excessive(
        project,
        request.estimated_hourly_burn_aud,
        excessive_hourly_burn_ratio,
    )

    baseline_allow = (
        product_allowed_by_plan
        and machine_allowed_by_baseline
        and not accelerator_requested
        and not burn_excessive
    )

    if baseline_allow:
        return RequestDecision(
            project_id=project.project_id,
            request_id=request.request_id,
            status=RequestStatus.ALLOW,
            allow=True,
            notify=False,
            reasons=("Request fits project plan and baseline policy.",),
            matched_approval_id=None,
        )

    matched_approval = find_matching_approval(
        approvals,
        project_id=request.project_id,
        product=request.product,
        machine_type=request.machine_type,
        accelerator_type=request.accelerator_type,
        when=request.requested_at,
        hourly_burn_aud=request.estimated_hourly_burn_aud,
    )

    if matched_approval is not None:
        return RequestDecision(
            project_id=project.project_id,
            request_id=request.request_id,
            status=RequestStatus.ALLOW_BY_EXCEPTION,
            allow=True,
            notify=False,
            reasons=(
                f"Request is allowed by project scoped approval '{matched_approval.approval_id}'.",
            ),
            matched_approval_id=matched_approval.approval_id,
        )

    if not product_allowed_by_plan:
        reasons.append(
            f"Product '{request.product}' is not listed in the project's planned products."
        )

    if not machine_allowed_by_baseline:
        reasons.append(
            f"Machine type '{request.machine_type}' violates baseline machine families "
            f"{baseline_machine_prefixes}."
        )

    if accelerator_requested:
        reasons.append(
            f"Accelerator '{request.accelerator_type}' requires a project scoped approval."
        )

    if burn_excessive:
        reasons.append(
            "Estimated hourly burn is too high relative to the project's monthly budget "
            "and requires explicit approval."
        )

    reasons.append("No active matching project scoped approval was found.")

    return RequestDecision(
        project_id=project.project_id,
        request_id=request.request_id,
        status=RequestStatus.DENY,
        allow=False,
        notify=True,
        reasons=tuple(reasons),
        matched_approval_id=None,
    )


def assess_runtime_scope(
    project: Project,
    snapshot: RuntimeSnapshot,
    approvals: Iterable[Approval],
    *,
    observed_at: datetime,
    allowed_regions: frozenset[str] = DEFAULT_ALLOWED_REGIONS,
    baseline_machine_prefixes: tuple[str, ...] = DEFAULT_BASELINE_MACHINE_PREFIXES,
    excessive_hourly_burn_ratio: float = DEFAULT_EXCESSIVE_HOURLY_BURN_RATIO,
) -> RuntimeScopeDecision:
    reasons: list[str] = []

    if snapshot.region not in allowed_regions:
        reasons.append(f"Region '{snapshot.region}' is not in allowed locations.")
        return RuntimeScopeDecision(
            allowed=False,
            allowed_by_exception=False,
            reasons=tuple(reasons),
            matched_approval_id=None,
        )

    product_allowed_by_plan = product_in_project_plan(project, snapshot.product)
    machine_allowed_by_baseline = machine_prefix_matches(
        snapshot.machine_type,
        baseline_machine_prefixes,
    )
    accelerator_present = snapshot.accelerator_type is not None
    burn_excessive = hourly_burn_is_excessive(
        project,
        snapshot.hourly_burn_rate_aud,
        excessive_hourly_burn_ratio,
    )

    baseline_allow = (
        product_allowed_by_plan
        and machine_allowed_by_baseline
        and not accelerator_present
        and not burn_excessive
    )

    if baseline_allow:
        return RuntimeScopeDecision(
            allowed=True,
            allowed_by_exception=False,
            reasons=(),
            matched_approval_id=None,
        )

    matched_approval = find_matching_approval(
        approvals,
        project_id=snapshot.project_id,
        product=snapshot.product,
        machine_type=snapshot.machine_type,
        accelerator_type=snapshot.accelerator_type,
        when=observed_at,
        hourly_burn_aud=snapshot.hourly_burn_rate_aud,
    )

    if matched_approval is not None:
        return RuntimeScopeDecision(
            allowed=True,
            allowed_by_exception=True,
            reasons=(),
            matched_approval_id=matched_approval.approval_id,
        )

    if not product_allowed_by_plan:
        reasons.append(
            f"Product '{snapshot.product}' is not listed in the project's planned products."
        )

    if not machine_allowed_by_baseline:
        reasons.append(
            f"Machine type '{snapshot.machine_type}' violates allowed machine families "
            f"{baseline_machine_prefixes}."
        )

    if accelerator_present:
        reasons.append(
            f"Accelerator '{snapshot.accelerator_type}' requires a project scoped approval."
        )

    if burn_excessive:
        reasons.append(
            "Runtime hourly burn is too high relative to the project's monthly budget "
            "and requires explicit approval."
        )

    reasons.append("No active matching project scoped approval was found.")

    return RuntimeScopeDecision(
        allowed=False,
        allowed_by_exception=False,
        reasons=tuple(reasons),
        matched_approval_id=None,
    )