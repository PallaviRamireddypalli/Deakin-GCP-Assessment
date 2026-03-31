from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from google.cloud import resourcemanager_v3

from .models import PrincipalMode
from .models import Project
from .models import UseCase


def _load_profiles(path: str | Path) -> dict[str, dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _parse_use_case(value: str) -> UseCase:
    return UseCase(value)


def _parse_principal_mode(value: str) -> PrincipalMode:
    return PrincipalMode(value)


class GcpProjectDiscovery:
    """
    Read-only project discovery adapter.

    It lists ACTIVE projects directly under one organization, then merges
    each discovered project with local governance metadata from a JSON file.
    """

    def __init__(
        self,
        *,
        organization_id: str,
        profile_path: str | Path,
    ) -> None:
        self.organization_id = organization_id
        self.profile_path = Path(profile_path)

    def discover_projects(self) -> list[Project]:
        profiles = _load_profiles(self.profile_path)
        client = resourcemanager_v3.ProjectsClient()

        parent = f"organizations/{self.organization_id}"
        request = resourcemanager_v3.ListProjectsRequest(parent=parent)

        discovered: list[Project] = []

        for item in client.list_projects(request=request):
            # item.state can be ACTIVE, DELETE_REQUESTED, etc.
            if str(item.state).upper().endswith("DELETE_REQUESTED"):
                continue

            project_id = item.project_id
            if not project_id:
                continue

            profile = profiles.get(project_id)
            if profile is None:
                # Skip projects that exist in GCP but are not yet enrolled
                # into our governance metadata file.
                continue

            # Parent is an org here, so folder_path is minimal for now.
            folder_path = ("organizations", self.organization_id)

            discovered.append(
                Project(
                    project_id=project_id,
                    name=item.display_name or project_id,
                    folder_path=folder_path,
                    use_case=_parse_use_case(profile["use_case"]),
                    principal_mode=_parse_principal_mode(profile["principal_mode"]),
                    principals=tuple(profile["principals"]),
                    budget_monthly_aud=float(profile.get("budget_monthly_aud", 0.0)),
                    budget_spent_aud=float(profile.get("budget_spent_aud", 0.0)),
                    active=bool(profile.get("active", True)),
                    planned_products=tuple(profile.get("planned_products", ())),
                    labels=dict(profile.get("labels", {})),
                )
            )

        return discovered