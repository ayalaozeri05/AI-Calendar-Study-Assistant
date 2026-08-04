"""User profile data access via Supabase."""

from uuid import UUID
from app.gateways.supabase_gateway import SupabaseGateway
from app.schemas.user_schema import UserProfileCreate


class UserRepository:
    def __init__(self, gateway: SupabaseGateway | None = None) -> None:
        self._gateway = gateway or SupabaseGateway()

    def create_user_profile(self, data: UserProfileCreate) -> dict:
        payload = data.model_dump(exclude_none=True)
        response = self._gateway.table("users_profile").insert(payload).execute()
        if hasattr(response, "data") and response.data:
            return response.data[0]
        elif isinstance(response, dict) and response.get("data"):
            return response["data"][0]
        raise Exception("Failed to insert user profile")

    def get_user_profile(self, user_id: UUID) -> dict | None:
        response = (
            self._gateway.table("users_profile")
            .select("*")
            .eq("id", str(user_id))
            .limit(1)
            .execute()
        )
        if hasattr(response, "data") and response.data:
            return response.data[0]
        elif isinstance(response, dict) and response.get("data"):
            return response["data"][0]
        return None

    def get_user_profile_by_email(self, email: str) -> dict | None:
        response = (
            self._gateway.table("users_profile")
            .select("*")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        if hasattr(response, "data") and response.data:
            return response.data[0]
        elif isinstance(response, dict) and response.get("data"):
            return response["data"][0]
        return None

    def update_telegram_chat_id(self, user_id: UUID, telegram_chat_id: str) -> dict:
        response = (
            self._gateway.table("users_profile")
            .update({"telegram_chat_id": telegram_chat_id})
            .eq("id", str(user_id))
            .execute()
        )
        if hasattr(response, "data") and response.data:
            return response.data[0]
        if isinstance(response, dict) and response.get("data"):
            return response["data"][0]
        raise RuntimeError("Failed to update telegram_chat_id")
