"""Study brief API routes."""

from fastapi import APIRouter, HTTPException

from app.schemas.brief_schema import (
    BriefRequest,
    BriefResponse,
    BriefType,
    SendTelegramRequest,
    SendTelegramResponse,
)
from app.services.study_brief_service import StudyBriefService

router = APIRouter(prefix="/briefs", tags=["briefs"])


@router.post("/today", response_model=BriefResponse)
def generate_today_brief(body: BriefRequest):
    """Build today's study brief from synced calendar events."""
    try:
        return StudyBriefService().generate_today_brief(body.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/weekly", response_model=BriefResponse)
def generate_weekly_brief(body: BriefRequest):
    """Build weekly study brief from synced calendar events."""
    try:
        return StudyBriefService().generate_weekly_brief(body.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/send-telegram", response_model=SendTelegramResponse)
def send_brief_to_telegram(body: SendTelegramRequest):
    """Generate and send a study brief to the user's Telegram chat."""
    try:
        return StudyBriefService().send_brief_to_telegram(
            body.user_id, body.brief_type, body.brief_text
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
