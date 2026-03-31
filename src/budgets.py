from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import Project, UseCase


@dataclass(frozen=True)
class BudgetPolicy:
    default_budget_by_use_case: dict[UseCase, float]
    fallback_default_budget_aud: float = 150.0


DEFAULT_BUDGET_POLICY = BudgetPolicy(
    default_budget_by_use_case={
        UseCase.PHD_RESEARCH: 150.0,
        UseCase.TEACHING_AND_LEARNING: 500.0,
        UseCase.GENERAL_RESEARCH: 800.0,
        UseCase.PROFESSIONAL_STAFF: 1000.0,
        UseCase.UNKNOWN: 150.0,
    },
    fallback_default_budget_aud=150.0,
)


def resolve_project_budget(
    project: Project,
    policy: BudgetPolicy = DEFAULT_BUDGET_POLICY,
) -> float:
    """
    Project explicit budget wins.
    Otherwise use the default for the project's use case.
    """
    if project.budget_monthly_aud > 0:
        return float(project.budget_monthly_aud)

    return float(
        policy.default_budget_by_use_case.get(
            project.use_case,
            policy.fallback_default_budget_aud,
        )
    )


def resolve_project_budget_spent(project: Project) -> float:
    return max(0.0, float(project.budget_spent_aud))


def clone_project_with_resolved_budget(
    project: Project,
    policy: BudgetPolicy = DEFAULT_BUDGET_POLICY,
) -> Project:
    """
    Returns a copy of the project with an effective monthly budget filled in.
    Useful when upstream data omitted the budget and we want deterministic engine behavior.
    """
    resolved_budget = resolve_project_budget(project, policy)

    return Project(
        project_id=project.project_id,
        name=project.name,
        folder_path=project.folder_path,
        use_case=project.use_case,
        principal_mode=project.principal_mode,
        principals=project.principals,
        budget_monthly_aud=resolved_budget,
        budget_spent_aud=resolve_project_budget_spent(project),
        active=project.active,
        planned_products=project.planned_products,
        labels=project.labels,
    )


def clone_projects_with_resolved_budgets(
    projects: list[Project],
    policy: BudgetPolicy = DEFAULT_BUDGET_POLICY,
) -> list[Project]:
    return [clone_project_with_resolved_budget(project, policy) for project in projects]