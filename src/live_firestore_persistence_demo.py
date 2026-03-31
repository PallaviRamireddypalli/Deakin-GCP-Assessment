from __future__ import annotations

from .firestore_state_store import FirestoreManagedProjectRegistry
from .firestore_state_store import FirestoreStateStore


def main() -> None:
    state_store = FirestoreStateStore()
    registry = FirestoreManagedProjectRegistry()

    state = state_store.load_state()
    managed_ids = registry.load_managed_project_ids()

    print("=== Firestore Persistence Demo ===")
    print(f"Loaded state resources: {len(state.resources)}")
    print(f"Loaded managed project IDs: {managed_ids}")

    updated_ids = set(managed_ids)
    updated_ids.add("YOUR_PROJECT_ID")
    registry.replace_managed_project_ids(updated_ids)

    managed_ids_after = registry.load_managed_project_ids()
    print(f"Managed project IDs after write: {managed_ids_after}")


if __name__ == "__main__":
    main()