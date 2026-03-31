from __future__ import annotations

from src.budgets import (
    BudgetPolicy,
    clone_project_with_resolved_budget,
    resolve_project_budget,
)
from src.models import PrincipalMode, Project, UseCase


def make_project(
    project_id: str,
    *,
    use_case: UseCase,
    budget_monthly_aud: float,
    budget_spent_aud: float = 0.0,
) -> Project:
    return Project(
        project_id=project_id,
        name=project_id,
        folder_path=("deakin.edu.au", "SEBE", "Eng"),
        use_case=use_case,
        principal_mode=PrincipalMode.ONE_TO_ONE,
        principals=("owner@example.edu",),
        budget_monthly_aud=budget_monthly_aud,
        budget_spent_aud=budget_spent_aud,
        active=True,
        planned_products=("COLAB_ENTERPRISE",),
    )


def test_explicit_project_budget_wins_over_default():
    policy = BudgetPolicy(
        default_budget_by_use_case={
            UseCase.PHD_RESEARCH: 150.0,
            UseCase.TEACHING_AND_LEARNING: 500.0,
            UseCase.GENERAL_RESEARCH: 800.0,
            UseCase.PROFESSIONAL_STAFF: 1000.0,
            UseCase.UNKNOWN: 150.0,
        }
    )

    project = make_project(
        "p1",
        use_case=UseCase.PHD_RESEARCH,
        budget_monthly_aud=275.0,
    )

    assert resolve_project_budget(project, policy) == 275.0


def test_phd_default_budget_is_used_when_project_budget_missing():
    project = make_project(
        "p1",
        use_case=UseCase.PHD_RESEARCH,
        budget_monthly_aud=0.0,
    )

    resolved = clone_project_with_resolved_budget(project)

    assert resolved.budget_monthly_aud == 150.0


def test_teaching_default_budget_is_used_when_project_budget_missing():
    project = make_project(
        "p2",
        use_case=UseCase.TEACHING_AND_LEARNING,
        budget_monthly_aud=0.0,
    )

    resolved = clone_project_with_resolved_budget(project)

    assert resolved.budget_monthly_aud == 500.0


def test_professional_staff_default_budget_is_used_when_project_budget_missing():
    project = make_project(
        "p3",
        use_case=UseCase.PROFESSIONAL_STAFF,
        budget_monthly_aud=0.0,
    )

    resolved = clone_project_with_resolved_budget(project)

    assert resolved.budget_monthly_aud == 1000.0


def test_unknown_use_case_falls_back_safely():
    policy = BudgetPolicy(
        default_budget_by_use_case={},
        fallback_default_budget_aud=150.0,
    )

    project = make_project(
        "p4",
        use_case=UseCase.UNKNOWN,
        budget_monthly_aud=0.0,
    )

    assert resolve_project_budget(project, policy) == 150.0


def test_negative_spent_budget_is_normalized_to_zero():
    project = make_project(
        "p5",
        use_case=UseCase.GENERAL_RESEARCH,
        budget_monthly_aud=0.0,
        budget_spent_aud=-20.0,
    )

    resolved = clone_project_with_resolved_budget(project)

    assert resolved.budget_spent_aud == 0.0