from __future__ import annotations

from dataclasses import dataclass, field

from .models import Project


@dataclass
class FolderNode:
    name: str
    projects: list[Project] = field(default_factory=list)
    children: list["FolderNode"] = field(default_factory=list)


@dataclass(frozen=True)
class RegistrySyncResult:
    to_onboard: tuple[str, ...]
    to_offboard: tuple[str, ...]
    unchanged: tuple[str, ...]


def discover_projects(root: FolderNode) -> list[Project]:
    """
    Recursively discover all projects across the entire folder tree.
    This is how we avoid blind spots.
    """
    discovered: list[Project] = []

    def walk(node: FolderNode) -> None:
        for project in node.projects:
            discovered.append(project)
        for child in node.children:
            walk(child)

    walk(root)
    return discovered


def sync_managed_projects(
    discovered_projects: list[Project],
    currently_managed_project_ids: set[str],
) -> RegistrySyncResult:
    """
    Decide which projects must be onboarded or offboarded automatically.
    """
    discovered_ids = {project.project_id for project in discovered_projects if project.active}

    to_onboard = tuple(sorted(discovered_ids - currently_managed_project_ids))
    to_offboard = tuple(sorted(currently_managed_project_ids - discovered_ids))
    unchanged = tuple(sorted(discovered_ids & currently_managed_project_ids))

    return RegistrySyncResult(
        to_onboard=to_onboard,
        to_offboard=to_offboard,
        unchanged=unchanged,
    )