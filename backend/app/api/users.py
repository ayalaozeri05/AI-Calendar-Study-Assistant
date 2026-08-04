"""User profile API routes."""

from uuid import UUID
from fastapi import APIRouter, HTTPException
from app.schemas.user_schema import UserProfileCreate, UserProfileResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserProfileResponse, status_code=201)
def create_user(data: UserProfileCreate):
    """Create a user profile."""
    try:
        return UserService().create_user_profile(data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/demo", response_model=UserProfileResponse, status_code=201)
def create_demo_user():
    """Create or return a demo user profile (applies DEMO_TELEGRAM_CHAT_ID from .env)."""
    try:
        return UserService().get_or_create_demo_user()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/by-email/{email}", response_model=UserProfileResponse)
def get_user_by_email(email: str):
    """Retrieve user profile by email if it exists."""
    try:
        # Use repository directly to search by email without creating
        row = UserService()._repository.get_user_profile_by_email(email)
        if row is None:
            raise HTTPException(status_code=404, detail="User not found")
        return UserProfileResponse.model_validate(row)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{user_id}", response_model=UserProfileResponse)
def get_user(user_id: UUID):
    """Retrieve user profile by user_id."""
    try:
        user = UserService().get_user_profile(user_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user
