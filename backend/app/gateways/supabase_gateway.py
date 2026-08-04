"""Supabase external-service gateway."""

from supabase import Client, create_client

from app.config import Settings, settings


class SupabaseGateway:
    """Centralizes all Supabase client access for the backend."""

    def __init__(self, app_settings: Settings | None = None) -> None:
        self._settings = app_settings or settings
        self._client: Client | None = None

    def _get_client(self) -> Client:
        if not self._settings.supabase_url or not self._settings.supabase_anon_key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")

        if self._client is None:
            self._client = create_client(
                self._settings.supabase_url,
                self._settings.supabase_anon_key,
            )
        return self._client

    def table(self, name: str):
        """Return a Supabase table query builder."""
        return self._get_client().table(name)

    def health_check(self) -> dict:
        """Probe Supabase with a minimal read against users_profile."""
        try:
            self.table("users_profile").select("id").limit(1).execute()
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
