from __future__ import annotations

from datetime import datetime
from src.models import ResourceStatus
from src.models import RuntimeSnapshot
import base64
import json
from typing import Any

import functions_framework
from src.firestore_state_store import FirestoreManagedProjectRegistry
from src.firestore_state_store import FirestoreStateStore
from src.gcp_project_discovery import GcpProjectDiscovery
from src.local_adapters import MemoryApprovalRepository
from src.local_adapters import MemoryNotifier
from src.local_adapters import MemoryProvisioningRequestRepository
from src.colab_runtime_controller import ColabRuntimeController
from src.local_adapters import MemoryRuntimeInventory
from src.orchestrator import orchestrate_cycle

ORG_ID = "YOUR_ORG_ID"
PROFILE_PATH = "data/project_profiles.json"


def _decode_pubsub_message(cloud_event: Any) -> dict[str, Any]:
    message_data = cloud_event.data.get("message", {})
    encoded = message_data.get("data")

    if not encoded:
        return {"type": "scheduled_sweep"}

    decoded = base64.b64decode(encoded).decode("utf-8")
    payload = json.loads(decoded)

    if isinstance(payload, dict):
        if "type" in payload:
            return payload
        if "logName" in payload and "protoPayload" in payload:
            payload["type"] = "log_event"
            return payload

    return {"type": "unknown", "raw": payload}

def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_status(value: str | None) -> ResourceStatus:
    if value is None:
        return ResourceStatus.RUNNING
    return ResourceStatus(value)


def _parse_runtime_snapshots(payload: dict[str, Any]) -> list[RuntimeSnapshot]:
    items = payload.get("runtime_snapshots", [])
    snapshots: list[RuntimeSnapshot] = []

    for item in items:
        last_activity_at_raw = item.get("last_activity_at")
        last_activity_at = None
        if last_activity_at_raw is not None:
            last_activity_at = _parse_datetime(last_activity_at_raw)

        snapshots.append(
            RuntimeSnapshot(
                resource_id=item["resource_id"],
                project_id=item["project_id"],
                product=item["product"],
                machine_type=item["machine_type"],
                region=item["region"],
                accelerator_type=item.get("accelerator_type"),
                status=_parse_status(item.get("status")),
                connected=bool(item.get("connected", True)),
                observed_at=_parse_datetime(item["observed_at"]),
                started_at=_parse_datetime(item["started_at"]),
                last_activity_at=last_activity_at,
                hourly_burn_rate_aud=float(item["hourly_burn_rate_aud"]),
            )
        )

    return snapshots


@functions_framework.cloud_event
def guardrail_entrypoint(cloud_event: Any) -> None:
    payload = _decode_pubsub_message(cloud_event)
    event_type = payload.get("type", "scheduled_sweep")

    print(f"Received event type: {event_type}")
    print(f"Payload: {payload}")

    project_discovery = GcpProjectDiscovery(
        organization_id=ORG_ID,
        profile_path=PROFILE_PATH,
    )

    approval_repository = MemoryApprovalRepository([])
    request_repository = MemoryProvisioningRequestRepository([])
    runtime_snapshots = _parse_runtime_snapshots(payload)
    runtime_inventory = MemoryRuntimeInventory(runtime_snapshots)
    runtime_controller = ColabRuntimeController()
    notifier = MemoryNotifier()
    state_store = FirestoreStateStore()
    managed_registry = FirestoreManagedProjectRegistry()

    result = orchestrate_cycle(
        project_discovery=project_discovery,
        approval_repository=approval_repository,
        request_repository=request_repository,
        runtime_inventory=runtime_inventory,
        runtime_controller=runtime_controller,
        notifier=notifier,
        state_store=state_store,
        managed_project_registry=managed_registry,
    )

    print(f"To onboard: {result.registry_sync.to_onboard}")
    print(f"To offboard: {result.registry_sync.to_offboard}")
    print(f"Managed registry now: {managed_registry.load_managed_project_ids()}")
    print(f"Request decisions: {len(result.request_decisions)}")
    print(f"Runtime decisions: {len(result.runtime_decisions)}")
    print(f"Action plans: {len(result.action_plans)}")
    print(f"Notifications emitted: {len(notifier.messages)}")
    print(f"Stop actions issued: {len(runtime_controller.stops)}")