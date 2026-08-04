"""User profile business logic."""

from uuid import UUID

from app.config import settings
from app.repositories.activity_repository import ActivityRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user_schema import UserProfileCreate, UserProfileResponse


class UserService:
    def __init__(
        self,
        repository: UserRepository | None = None,
        activity_repository: ActivityRepository | None = None,
    ) -> None:
        self._repository = repository or UserRepository()
        self._activity = activity_repository or ActivityRepository()

    def create_user_profile(self, data: UserProfileCreate) -> UserProfileResponse:
        """Create a new user profile and log the activity event."""
        row = self._repository.create_user_profile(data)
        user = UserProfileResponse.model_validate(row)

        self._activity.log_event(
            user_id=user.id,
            event_type="user_created",
            entity_type="users_profile",
            entity_id=user.id,
            description=f"User profile created: {user.email}",
        )
        return user

    def get_user_profile(self, user_id: UUID) -> UserProfileResponse | None:
        """Retrieve a user profile by ID."""
        row = self._repository.get_user_profile(user_id)
        if row is None:
            return None
        return UserProfileResponse.model_validate(row)

    def get_or_create_user_profile_by_email(
        self,
        email: str,
        full_name: str | None = None,
        telegram_chat_id: str | None = None,
    ) -> UserProfileResponse:
        """Get an existing user profile by email or create a new one if not found."""
        row = self._repository.get_user_profile_by_email(email)
        if row is not None:
            user = UserProfileResponse.model_validate(row)
            if telegram_chat_id and (
                not user.telegram_chat_id or user.telegram_chat_id != telegram_chat_id
            ):
                updated = self._repository.update_telegram_chat_id(
                    user.id, telegram_chat_id
                )
                return UserProfileResponse.model_validate(updated)
            return user

        create_data = UserProfileCreate(
            email=email,
            full_name=full_name,
            telegram_chat_id=telegram_chat_id,
        )
        return self.create_user_profile(create_data)

    def sync_telegram_chat_id_from_env(self, user: UserProfileResponse) -> UserProfileResponse:
        """Apply DEMO_TELEGRAM_CHAT_ID from .env when configured."""
        chat_id = settings.demo_telegram_chat_id.strip()
        if not chat_id:
            return user
        if not user.telegram_chat_id or user.telegram_chat_id != chat_id:
            updated = self._repository.update_telegram_chat_id(user.id, chat_id)
            return UserProfileResponse.model_validate(updated)
        return user

    def sync_telegram_chat_id_from_env_by_id(
        self, user_id: UUID
    ) -> UserProfileResponse | None:
        user = self.get_user_profile(user_id)
        if user is None:
            return None
        return self.sync_telegram_chat_id_from_env(user)

    def get_or_create_demo_user(self) -> UserProfileResponse:
        """Demo student used by the desktop dashboard."""
        chat_id = settings.demo_telegram_chat_id.strip() or None
        user = self.get_or_create_user_profile_by_email(
            email="demo@student.local",
            full_name="Demo Student",
            telegram_chat_id=chat_id,
        )
        # Always re-apply DEMO_TELEGRAM_CHAT_ID from .env when configured.
        return self.sync_telegram_chat_id_from_env(user)
