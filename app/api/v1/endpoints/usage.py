from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.models import User
from app.schemas.usage import UsageResponse
from app.services.usage_service import get_usage_info

router = APIRouter()


@router.get("/usage", response_model=UsageResponse)
async def get_my_usage(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    info = await get_usage_info(db, current_user)
    await db.commit()
    return info
