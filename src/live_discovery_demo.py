from __future__ import annotations

from .gcp_project_discovery import GcpProjectDiscovery


def main() -> None:
    organization_id = "YOUR_ORG_ID"

    adapter = GcpProjectDiscovery(
        organization_id=organization_id,
        profile_path="data/project_profiles.json",
    )

    projects = adapter.discover_projects()

    print(f"Discovered governed projects: {len(projects)}")
    for project in projects:
        print(
            f"- {project.project_id} | "
            f"name={project.name} | "
            f"use_case={project.use_case} | "
            f"budget={project.budget_monthly_aud}"
        )


if __name__ == "__main__":
    main()