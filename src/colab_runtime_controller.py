from __future__ import annotations

import os
from typing import Final

import google.auth
from google.auth.transport.requests import AuthorizedSession


NOTEBOOK_STOP_SCOPE: Final[str] = "https://www.googleapis.com/auth/cloud-platform"
REAL_STOP_ENV: Final[str] = "GUARDRAIL_REAL_STOP"


def _is_real_stop_enabled() -> bool:
    value = os.getenv(REAL_STOP_ENV, "false").strip().lower()
    return value in {"1", "true", "yes", "y"}


def _looks_like_full_runtime_name(resource_id: str) -> bool:
    return (
        resource_id.startswith("projects/")
        and "/locations/" in resource_id
        and "/notebookRuntimes/" in resource_id
    )


class ColabRuntimeController:
    """
    Real Colab / Notebook runtime controller.

    Default behavior:
      dry run only

    Real stop behavior:
      set GUARDRAIL_REAL_STOP=true
      and pass a full runtime resource name as resource_id, for example:
      projects/PROJECT_ID/locations/REGION/notebookRuntimes/RUNTIME_ID
    """

    def __init__(self) -> None:
        self.real_stop = _is_real_stop_enabled()
        self.dry_run_actions: list[tuple[str, str, tuple[str, ...]]] = []
        self.real_stop_actions: list[tuple[str, str, tuple[str, ...]]] = []
        self.stops: list[tuple[str, str, tuple[str, ...]]] = []

    def stop_runtime(
        self,
        project_id: str,
        resource_id: str,
        reasons: tuple[str, ...],
    ) -> None:
        if not self.real_stop:
            print(
                f"DRY_RUN_STOP project_id={project_id} resource_id={resource_id} reasons={reasons}"
            )
            action = (project_id, resource_id, reasons)
            self.dry_run_actions.append(action)
            self.stops.append(action)
            return

        if not _looks_like_full_runtime_name(resource_id):
            raise ValueError(
                "Real stop requires resource_id to be a full notebook runtime name like "
                "'projects/PROJECT_ID/locations/REGION/notebookRuntimes/RUNTIME_ID'."
            )

        credentials, _ = google.auth.default(scopes=[NOTEBOOK_STOP_SCOPE])
        session = AuthorizedSession(credentials)

        url = f"https://notebooks.googleapis.com/v1/{resource_id}:stop"
        response = session.post(url, json={})

        if response.status_code >= 400:
            raise RuntimeError(
                f"Notebook runtime stop failed: status={response.status_code}, body={response.text}"
            )

        print(
            f"REAL_STOP_TRIGGERED project_id={project_id} resource_id={resource_id} reasons={reasons}"
        )
        action = (project_id, resource_id, reasons)
        self.real_stop_actions.append(action)
        self.stops.append(action)