from __future__ import annotations

import base64
from datetime import datetime, timezone

from google.cloud import firestore

from .state import EngineState
from .state import ResourceState
from .state import make_resource_key
from .models import Severity


def _dt_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _iso_to_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)

def _key_to_doc_id(key: str) -> str:
    encoded = base64.urlsafe_b64encode(key.encode("utf-8")).decode("ascii")
    return "b64_" + encoded.rstrip("=")


def _doc_id_to_key(doc_id: str) -> str:
    if not doc_id.startswith("b64_"):
        return doc_id

    raw = doc_id[4:]
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode((raw + padding).encode("ascii")).decode("utf-8")


class FirestoreStateStore:
    """
    Persists EngineState in Firestore.

    Collection:
      guardrail_state_resources

    Document ID:
      {project_id}:{resource_id}
    """

    def __init__(self) -> None:
        self.client = firestore.Client()
        self.collection = self.client.collection("guardrail_state_resources")

    def load_state(self) -> EngineState:
        state = EngineState()

        for doc in self.collection.stream():
            data = doc.to_dict() or {}
            key = _doc_id_to_key(doc.id)

            state.resources[key] = ResourceState(
                last_notification_at=_iso_to_dt(data.get("last_notification_at")),
                last_stop_at=_iso_to_dt(data.get("last_stop_at")),
                last_seen_at=_iso_to_dt(data.get("last_seen_at")),
                last_decision_severity=Severity(data.get("last_decision_severity", "OK")),
            )

        return state

    def save_state(self, state: EngineState) -> None:
        for key, resource_state in state.resources.items():
           doc_id = _key_to_doc_id(key)

        self.collection.document(doc_id).set(
                {
                    "last_notification_at": _dt_to_iso(resource_state.last_notification_at),
                    "last_stop_at": _dt_to_iso(resource_state.last_stop_at),
                    "last_seen_at": _dt_to_iso(resource_state.last_seen_at),
                    "last_decision_severity": resource_state.last_decision_severity.value,
                }
            )


class FirestoreManagedProjectRegistry:
    """
    Persists managed project IDs in Firestore.

    Collection:
      guardrail_registry

    Document ID:
      managed_projects
    """

    def __init__(self) -> None:
        self.client = firestore.Client()
        self.doc_ref = self.client.collection("guardrail_registry").document("managed_projects")

    def load_managed_project_ids(self) -> set[str]:
        snapshot = self.doc_ref.get()
        if not snapshot.exists:
            return set()

        data = snapshot.to_dict() or {}
        return set(data.get("project_ids", []))

    def replace_managed_project_ids(self, project_ids: set[str]) -> None:
        self.doc_ref.set(
            {
                "project_ids": sorted(project_ids),
            }
        )