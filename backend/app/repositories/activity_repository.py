"""Activity event data access via Supabase (MVP Event Sourcing)."""

from uuid import UUID

from app.gateways.supabase_gateway import SupabaseGateway


class ActivityRepository:
    def __init__(self, gateway: SupabaseGateway | None = None) -> None:
        self._gateway = gateway or SupabaseGateway()

    def log_event(
        self,
        user_id: UUID,
        event_type: str,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        description: str | None = None,
    ) -> dict:
        payload = {
            "user_id": str(user_id),
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id else None,
            "description": description,
        }
        response = self._gateway.table("activity_events").insert(payload).execute()
        if hasattr(response, "data") and response.data:
            return response.data[0]
        if isinstance(response, dict) and response.get("data"):
            return response["data"][0]
        raise RuntimeError("Failed to insert activity event")
